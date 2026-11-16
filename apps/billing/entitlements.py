"""Entitlement checks — single source of truth for Free / Plus / Premium gating.

Tiers:
  free      — basic search, dish pages, pantry (no quantity tracking), save up to 20
  plus      — KES 499/month: everything in free + quantity pantry, can-make, meal plans,
              shopping lists, budget mode, nutrition details, unlimited saves, no ads
  premium   — KES 999/month: everything in plus + priority search ranking, offline sync,
              advanced analytics, early access features

Usage:
    from apps.billing.entitlements import RequiresPlus, RequiresPremium

    class MealPlanView(APIView):
        permission_classes = [IsAuthenticated, RequiresPlus]
"""

from rest_framework.permissions import BasePermission

# Free tier save limit
FREE_SAVE_LIMIT = 20

# Features gated behind Plus
PLUS_FEATURES = frozenset([
    "quantity_pantry",
    "can_make",
    "meal_plans",
    "shopping_lists",
    "nutrition_details",
    "budget_mode",
    "unlimited_saves",
    "no_ads",
])

# Features gated behind Premium (superset of Plus)
PREMIUM_FEATURES = frozenset([
    *PLUS_FEATURES,
    "priority_search",
    "offline_sync",
    "advanced_analytics",
    "early_access",
])


def user_has_active_plus(user) -> bool:
    """Return True if the user has an active Plus or Premium subscription."""
    if not user or not user.is_authenticated:
        return False
    try:
        sub = user.subscription
        return sub.is_active_plus()
    except Exception:
        return False


def user_has_active_premium(user) -> bool:
    """Return True if the user has an active Premium subscription."""
    if not user or not user.is_authenticated:
        return False
    try:
        sub = user.subscription
        return sub.is_active_premium()
    except Exception:
        return False


class RequiresPlus(BasePermission):
    """DRF permission: request must come from a user with Plus or Premium subscription."""

    message = {
        "error": {
            "code": "plus_required",
            "message": (
                "This feature requires Flavor Find Plus. "
                "Subscribe at /v1/subscribe/ from KES 499/month."
            ),
        }
    }

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return user_has_active_plus(request.user)


class RequiresPremium(BasePermission):
    """DRF permission: request must come from a user with a Premium subscription."""

    message = {
        "error": {
            "code": "premium_required",
            "message": (
                "This feature requires Flavor Find Premium. "
                "Subscribe at /v1/subscribe/ for KES 999/month."
            ),
        }
    }

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return user_has_active_premium(request.user)
