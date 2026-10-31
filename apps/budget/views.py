"""Budget mode — find recipes within a KES budget."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.entitlements import RequiresPlus
from apps.search.services import ALLERGEN_DISCLAIMER, get_user_diet_tags


class BudgetSuggestSerializer(serializers.Serializer):
    budget_kes = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Maximum cost per serving in KES (estimate only).",
    )
    servings = serializers.IntegerField(min_value=1, max_value=20, default=1)
    mode = serializers.ChoiceField(choices=["strict", "explore"], default="strict")
    lang = serializers.ChoiceField(choices=["en", "sw"], default="en")
    limit = serializers.IntegerField(min_value=1, max_value=50, default=20)


class BudgetSuggestView(APIView):
    """POST /v1/budget/suggest/ — recipes within a KES budget per serving."""

    permission_classes = [IsAuthenticated, RequiresPlus]

    @extend_schema(
        request=BudgetSuggestSerializer,
        responses={200: {"type": "object"}},
        summary="Budget mode recipe suggestions",
        description=(
            "Returns recipes whose estimated cost per serving is within the given budget. "
            "Cost estimates come from the engine and are always labelled as estimates. "
            "Diet and allergen exclusions from your profile are always applied. "
            "Requires Plus subscription."
        ),
    )
    def post(self, request):
        ser = BudgetSuggestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        from apps.engine_client.client import engine
        from apps.pantry.models import PantryItem

        diet = get_user_diet_tags(request.user)
        pantry_slugs = list(
            PantryItem.objects.filter(user=request.user).values_list("ingredient_slug", flat=True)
        )

        # Engine search with cost filter
        result = engine.search(
            ingredients=pantry_slugs,
            diet=diet,
            mode=ser.validated_data["mode"],
            lang=ser.validated_data["lang"],
            limit=ser.validated_data["limit"],
        )

        # Filter results by cost estimate
        budget = float(ser.validated_data["budget_kes"])
        servings = ser.validated_data["servings"]
        budget_per_serving = budget / servings

        for tier in ("exact", "can_make", "almost"):
            dishes = result.get("results", {}).get(tier, [])
            result.setdefault("results", {})[tier] = [
                d
                for d in dishes
                if (
                    d.get("cost_estimate_kes") is None
                    or float(d["cost_estimate_kes"]) <= budget_per_serving
                )
            ]

        result["allergen_disclaimer"] = ALLERGEN_DISCLAIMER
        result["cost_disclaimer"] = (
            "Cost estimates are for guidance only and based on typical market prices. "
            "Actual prices may vary."
        )
        result["budget_kes"] = str(ser.validated_data["budget_kes"])

        return Response(result)
