"""Planner service — shopping list generation and WhatsApp share text."""

import re
from datetime import date, timedelta


def parse_iso_week(week_str: str) -> date:
    """Parse YYYY-Www into the Monday date of that week.

    e.g. '2026-W44' → date(2026, 10, 26)
    """
    match = re.match(r"^(\d{4})-W(\d{1,2})$", week_str)
    if not match:
        raise ValueError(f"Invalid week format: {week_str!r}. Expected YYYY-Www.")
    year = int(match.group(1))
    week = int(match.group(2))
    # ISO week 1 of year is the week containing Jan 4th
    jan4 = date(year, 1, 4)
    week1_monday = jan4 - timedelta(days=jan4.weekday())
    monday = week1_monday + timedelta(weeks=week - 1)
    return monday


def date_to_iso_week(d) -> str:
    """Convert a Monday date back to YYYY-Www format."""
    from datetime import date

    if isinstance(d, str):
        d = date.fromisoformat(d)
    return f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"


def generate_shopping_list(plan, user) -> list[dict]:
    """Generate a deduplicated ingredient list from a meal plan.

    For each dish in the plan, calls engine.get_missing() with the user's
    current pantry to get only the ingredients they need to buy.

    Returns a list of dicts ready to create ShoppingItem records.
    """
    from apps.engine_client.client import engine
    from apps.pantry.models import PantryItem

    pantry_ids = list(PantryItem.objects.filter(user=user).values_list("ingredient_id", flat=True))

    # Collect unique dish slugs with their total servings
    dish_servings: dict[str, int] = {}
    dish_slugs: dict[str, str] = {}  # slug → id
    for entry in plan.entries.all():
        slug = entry.dish_slug
        dish_servings[slug] = dish_servings.get(slug, 0) + entry.servings
        dish_slugs[slug] = entry.dish_id

    # Get missing ingredients for each dish
    seen_ingredient_ids: set[str] = set()
    items = []
    position = 0

    for slug in dish_slugs:
        try:
            missing = engine.get_missing(slug=slug, pantry_ingredient_ids=pantry_ids)
            for ingredient in missing.get("missing", []):
                iid = ingredient.get("id") or ingredient.get("ingredient_id", "")
                if iid in seen_ingredient_ids:
                    continue
                seen_ingredient_ids.add(iid)
                items.append(
                    {
                        "ingredient_id": iid,
                        "ingredient_slug": ingredient.get("slug", ""),
                        "display_name": ingredient.get("name_en", ingredient.get("name", "")),
                        "quantity_note": "",
                        "price_estimate_kes": ingredient.get("cost_estimate_kes"),
                        "position": position,
                    }
                )
                position += 1
        except Exception:
            # Engine unavailable — skip this dish, continue with others
            pass

    return items


def shopping_list_to_whatsapp(shopping_list) -> str:
    """Format a shopping list as WhatsApp-ready plain text.

    Example output:
        Flavor Find Shopping List — Week 44

        ☐ Sukuma wiki (500g) ~KES 30
        ☐ Maize flour (2kg) ~KES 140

        Total estimate: ~KES 170
        (Prices are estimates only)
    """
    lines = []

    week_label = ""
    if shopping_list.plan:
        from apps.planner.services import date_to_iso_week

        week_str = date_to_iso_week(shopping_list.plan.week_start)
        week_label = f" — {week_str}"

    lines.append(f"Flavor Find Shopping List{week_label}")
    lines.append("")

    total = 0
    has_estimates = False

    for item in shopping_list.items.all().order_by("position", "display_name"):
        check = "✓" if item.checked else "☐"
        qty = f" ({item.quantity_note})" if item.quantity_note else ""
        price = ""
        if item.price_estimate_kes is not None:
            price = f" ~KES {int(item.price_estimate_kes)}"
            total += int(item.price_estimate_kes)
            has_estimates = True
        lines.append(f"{check} {item.display_name}{qty}{price}")

    if has_estimates:
        lines.append("")
        lines.append(f"Total estimate: ~KES {total}")
        lines.append("(Prices are estimates only)")

    return "\n".join(lines)
