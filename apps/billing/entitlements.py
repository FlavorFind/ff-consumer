"""Entitlement checks — single source of truth for Free vs Plus gating.

Import `requires_plus` and use it as a DRF permission class.
Never duplicate entitlement logic in views.

Usage:
    from apps.billing.entitlements import RequiresPlus

    class MealPlanView(APIView):
        permission_classes = [IsAuthenticated, RequiresPlus]
"""

from rest_framework.permissions import BasePermission

# Features gated behind Plus
PLUS_FEATURES = frozenset(
    [
        "meal_plans",
        "shopping_lists",
        "nutrition_details",
        "budget_mode",
        "offline_sync",
        "unlimited_saves",
    ]
)

# Free tier save limit
FREE_SAVE_LIMIT = 20


def user_has_active_plus(user) -> bool:
    """Return True if the user has an active or trialing Plus subscription."""
    if not user or not user.is_authenticated:
        return False
    try:
        sub = user.subscription
        return sub.is_active_plus()
    except Exception:
        return False


class RequiresPlus(BasePermission):
    """DRF permission: request must come from a user with an active Plus subscription.

    Returns 403 with a clear message if the user is on the Free plan.
    """

    message = {
        "error": {
            "code": "plus_required",
            "message": (
                "This feature requires Flavor Find Plus. "
                "Subscribe at /v1/subscribe/ for KES 199/month."
            ),
        }
    }

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return user_has_active_plus(request.user)
