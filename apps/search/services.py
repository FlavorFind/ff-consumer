"""Search service — the ONLY place that calls engine search.

Safety invariant: diet tags are ALWAYS injected from the user's profile_diet.
This cannot be bypassed from the view layer.

A user with allergen exclusions in their profile can NEVER trigger a search
without those exclusions in the `diet` list sent to the engine.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.accounts.models import CustomUser

logger = logging.getLogger(__name__)

# Allergen disclaimer required on every response mentioning dietary info
ALLERGEN_DISCLAIMER = (
    "Allergen information is for guidance only. "
    "Always confirm with the kitchen before ordering."
)


def get_user_diet_tags(user: "CustomUser") -> list[str]:
    """Return all diet tag slugs for the user — both preferences and allergen exclusions.

    This is the authoritative source of diet restrictions for engine calls.
    """
    return list(user.diet_tags.values_list("diet_tag_slug", flat=True))


def search(
    user: "CustomUser",
    ingredients: list[str],
    mode: str = "strict",
    exclude: list[str] | None = None,
    lang: str = "en",
    limit: int = 20,
    meal_type: str | None = None,
    boost_region: bool = True,
) -> dict:
    """Perform a personalised search.

    - Injects pantry items into the ingredient list
    - ALWAYS injects diet tags from the user's profile
    - Applies a personalisation boost by region

    Returns the engine response augmented with:
    - allergen_disclaimer: always present
    - engine_status: "ok" or "degraded"
    """
    from apps.engine_client.client import engine
    from apps.pantry.models import PantryItem

    # 1. Get user's diet tags — SAFETY CRITICAL
    diet = get_user_diet_tags(user)

    # 2. Inject pantry items (slugs the engine understands)
    pantry_slugs = list(
        PantryItem.objects.filter(user=user).values_list("ingredient_slug", flat=True)
    )
    # Merge pantry with explicit ingredients, deduplicating
    all_ingredients = list(dict.fromkeys(ingredients + pantry_slugs))

    # 3. Call the engine
    result = engine.search(
        ingredients=all_ingredients,
        diet=diet,
        mode=mode,
        exclude=exclude,
        lang=lang,
        limit=limit,
        meal_type=meal_type,
    )

    # 4. Personalisation: boost results from user's preferred region
    if boost_region and result.get("results"):
        try:
            region_slug = user.profile.region_slug
            if region_slug:
                result = _boost_region(result, region_slug)
        except Exception:
            pass  # No profile yet — skip boost silently

    # 5. Always attach allergen disclaimer
    result["allergen_disclaimer"] = ALLERGEN_DISCLAIMER

    return result


def _boost_region(result: dict, region_slug: str) -> dict:
    """Bump dishes from the user's region to the top of each tier.

    Non-destructive — dishes that don't match stay in place.
    """
    for tier in ("exact", "can_make", "almost"):
        dishes = result.get("results", {}).get(tier, [])
        if not dishes:
            continue
        regional = [d for d in dishes if d.get("region_slug") == region_slug]
        others = [d for d in dishes if d.get("region_slug") != region_slug]
        result["results"][tier] = regional + others
    return result


def resolve(tokens: list[str], lang: str = "en") -> dict:
    """Resolve free-text tokens to engine ingredient IDs.

    The caller MUST check the response for `ambiguous` tokens and surface
    the choices to the user before calling search().
    Never pass an ambiguous token straight to search.
    """
    from apps.engine_client.client import engine

    return engine.resolve(tokens=tokens, lang=lang)


def get_ingredients(q: str, lang: str = "en") -> dict:
    """Autocomplete ingredient search. Cached in the engine client."""
    from apps.engine_client.client import engine

    return engine.get_ingredients(q=q, lang=lang)


def get_dish(slug: str, lang: str = "en") -> dict:
    """Fetch dish detail. Cached per slug + dataset_version."""
    from apps.engine_client.client import engine

    result = engine.get_dish(slug=slug, lang=lang)
    # Attach allergen disclaimer when dietary info is present
    if result.get("diet_tags") or result.get("allergen_notes"):
        result["allergen_disclaimer"] = ALLERGEN_DISCLAIMER
    return result
