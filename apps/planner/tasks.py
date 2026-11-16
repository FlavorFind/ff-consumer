"""Planner Celery tasks — meal reminders, pantry deduction, buy-ahead alerts."""

import logging
from datetime import date, timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


def _send_in_app_notification(user, ntype: str, title: str, body: str, data: dict | None = None):
    from apps.notifications.models import Notification

    Notification.objects.create(
        user=user,
        channel=Notification.Channel.IN_APP,
        type=ntype,
        title=title,
        body=body,
        data=data or {},
        sent_at=timezone.now(),
    )


@shared_task(name="apps.planner.tasks.send_meal_reminders")
def send_meal_reminders():
    """Daily task — for each user with a planned meal tomorrow, check whether
    all required ingredients are in their pantry.

    For each ingredient that is MISSING from the pantry, fire one in-app
    notification: "Buy {ingredient} today — you're making {dish} tomorrow."

    Runs at 8:00 AM Nairobi time daily (configured in CELERY_BEAT_SCHEDULE).
    """
    from apps.engine_client.client import engine
    from apps.pantry.models import PantryItem
    from apps.planner.models import MealPlan, MealPlanEntry
    from apps.planner.services import parse_iso_week

    tomorrow = date.today() + timedelta(days=1)
    # Map Python weekday (0=Monday) to our day codes
    day_code = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][tomorrow.weekday()]

    # Get all plan entries for tomorrow across all users (batch)
    # week_start is always a Monday — find the Monday of tomorrow's week
    week_monday = tomorrow - timedelta(days=tomorrow.weekday())

    entries = (
        MealPlanEntry.objects.filter(
            plan__week_start=week_monday,
            day=day_code,
        )
        .select_related("plan__user")
        .prefetch_related()
    )

    # Group by user
    user_entries: dict = {}
    for entry in entries:
        user = entry.plan.user
        user_entries.setdefault(user, []).append(entry)

    for user, user_day_entries in user_entries.items():
        pantry_slugs = set(
            PantryItem.objects.filter(user=user).values_list("ingredient_slug", flat=True)
        )

        for entry in user_day_entries:
            # Ask engine what's missing for this dish given the user's pantry
            try:
                missing_data = engine.get_missing(
                    slug=entry.dish_slug,
                    pantry_ingredient_ids=list(pantry_slugs),
                )
                missing = missing_data.get("missing", [])
            except Exception as exc:
                logger.warning(
                    "Engine error for dish %s (user %s): %s",
                    entry.dish_slug, user.id, exc,
                )
                continue

            if not missing:
                continue

            # Fire one notification per missing ingredient (deduplicate within 24h)
            dish_name = entry.dish_slug.replace("-", " ").title()
            missing_names = [
                m.get("name_en") or m.get("name", m.get("slug", "?")) for m in missing
            ]
            names_str = ", ".join(missing_names[:4])
            if len(missing_names) > 4:
                names_str += f" +{len(missing_names) - 4} more"

            # Single notification per dish-day pairing (not per ingredient)
            already_sent = _already_notified(user, "buy_reminder", entry.dish_slug)
            if already_sent:
                continue

            _send_in_app_notification(
                user=user,
                ntype="buy_reminder",
                title=f"Buy today for tomorrow: {dish_name}",
                body=(
                    f"You're making {dish_name} tomorrow but you're missing: {names_str}. "
                    "Add them to your shopping list now."
                ),
                data={
                    "dish_slug": entry.dish_slug,
                    "day": entry.day,
                    "meal_type": entry.meal_type,
                    "missing_slugs": [m.get("slug", "") for m in missing],
                },
            )
            logger.info(
                "Buy-reminder sent: user=%s dish=%s missing=%s",
                user.id, entry.dish_slug, missing_names,
            )


def _already_notified(user, ntype: str, dish_slug: str) -> bool:
    """True if a notification of this type for this dish was sent in the last 20 hours."""
    from apps.notifications.models import Notification

    cutoff = timezone.now() - timedelta(hours=20)
    return Notification.objects.filter(
        user=user,
        type=ntype,
        created_at__gte=cutoff,
        data__dish_slug=dish_slug,
    ).exists()


@shared_task(name="apps.planner.tasks.deduct_pantry_on_check")
def deduct_pantry_on_check(user_id: str, ingredient_slug: str, quantity_to_deduct=None):
    """When a shopping list item is checked off, reduce that ingredient's
    pantry quantity by the amount purchased (or by 1 unit if no quantity
    tracking is set up).

    Called by ShoppingItemCheckView when checked=True.
    """
    from decimal import Decimal

    from apps.pantry.models import PantryItem
    from apps.pantry.tasks import check_single_item_low_stock

    try:
        item = PantryItem.objects.get(user_id=user_id, ingredient_slug=ingredient_slug)
    except PantryItem.DoesNotExist:
        # Ingredient not in pantry — nothing to deduct, but we could auto-add it
        return

    if item.quantity is None:
        # Quantity tracking not set up — nothing to deduct
        return

    deduct = Decimal(str(quantity_to_deduct)) if quantity_to_deduct else Decimal("1")
    item.quantity = max(Decimal("0"), item.quantity - deduct)
    item.save(update_fields=["quantity"])

    # Check if now below threshold
    check_single_item_low_stock.delay(str(item.id))

    logger.info(
        "Pantry deducted: user=%s ingredient=%s deduct=%s new_qty=%s",
        user_id, ingredient_slug, deduct, item.quantity,
    )
