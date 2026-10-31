"""Planner views — meal plans and shopping lists."""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.entitlements import RequiresPlus
from apps.planner.models import MealPlan, MealPlanEntry, ShoppingItem, ShoppingList
from apps.planner.serializers import (
    MealPlanSerializer,
    MealPlanWriteSerializer,
    ShoppingItemSerializer,
    ShoppingListSerializer,
)
from apps.planner.services import (
    generate_shopping_list,
    parse_iso_week,
    shopping_list_to_whatsapp,
)


class MealPlanView(APIView):
    """GET and PUT a weekly meal plan. Week format: YYYY-Www."""

    permission_classes = [IsAuthenticated, RequiresPlus]

    @extend_schema(
        responses={200: MealPlanSerializer},
        summary="Get meal plan for a week",
        description="Week format: YYYY-Www (e.g. 2026-W44). Requires Plus subscription.",
    )
    def get(self, request, week):
        try:
            monday = parse_iso_week(week)
        except ValueError as exc:
            return Response(
                {"error": {"code": "bad_request", "message": str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plan, _ = MealPlan.objects.get_or_create(user=request.user, week_start=monday)
        return Response(MealPlanSerializer(plan).data)

    @extend_schema(
        request=MealPlanWriteSerializer,
        responses={200: MealPlanSerializer},
        summary="Set meal plan for a week",
        description=(
            "Replaces all entries for the week. "
            "Partial updates not supported — send the full plan. Requires Plus."
        ),
    )
    def put(self, request, week):
        try:
            monday = parse_iso_week(week)
        except ValueError as exc:
            return Response(
                {"error": {"code": "bad_request", "message": str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = MealPlanWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        plan, _ = MealPlan.objects.get_or_create(user=request.user, week_start=monday)

        # Replace all entries
        plan.entries.all().delete()
        for i, entry_data in enumerate(ser.validated_data["entries"]):
            MealPlanEntry.objects.create(
                plan=plan,
                day=entry_data["day"],
                meal_type=entry_data["meal_type"],
                dish_id=entry_data["dish_id"],
                dish_slug=entry_data["dish_slug"],
                servings=entry_data.get("servings", 1),
                note=entry_data.get("note", ""),
                position=entry_data.get("position", i),
            )

        plan.refresh_from_db()
        return Response(MealPlanSerializer(plan).data)


class ShoppingListGenerateView(APIView):
    """POST /v1/plans/<plan_id>/shopping-list/ — generate from plan."""

    permission_classes = [IsAuthenticated, RequiresPlus]

    @extend_schema(
        request=None,
        responses={201: ShoppingListSerializer},
        summary="Generate shopping list from meal plan",
        description=(
            "Calls the engine's missing endpoint for each dish in the plan "
            "and generates a deduplicated shopping list. Requires Plus."
        ),
    )
    def post(self, request, plan_id):
        try:
            plan = MealPlan.objects.get(id=plan_id, user=request.user)
        except MealPlan.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        shopping_list = ShoppingList.objects.create(
            user=request.user,
            plan=plan,
            name=f"Week of {plan.week_start}",
        )

        items = generate_shopping_list(plan, request.user)
        for item_data in items:
            ShoppingItem.objects.create(shopping_list=shopping_list, **item_data)

        shopping_list.refresh_from_db()
        return Response(ShoppingListSerializer(shopping_list).data, status=status.HTTP_201_CREATED)


class ShoppingListDetailView(APIView):
    """GET /v1/shopping-lists/<id>/"""

    permission_classes = [IsAuthenticated, RequiresPlus]

    @extend_schema(responses={200: ShoppingListSerializer}, summary="Get a shopping list")
    def get(self, request, list_id):
        try:
            sl = ShoppingList.objects.get(id=list_id, user=request.user)
        except ShoppingList.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(ShoppingListSerializer(sl).data)


class ShoppingItemCheckView(APIView):
    """PATCH /v1/shopping-lists/<id>/items/<item_id>/ — check/uncheck an item."""

    permission_classes = [IsAuthenticated, RequiresPlus]

    @extend_schema(
        request=ShoppingItemSerializer,
        responses={200: ShoppingItemSerializer},
        summary="Check or uncheck a shopping list item",
    )
    def patch(self, request, list_id, item_id):
        try:
            sl = ShoppingList.objects.get(id=list_id, user=request.user)
            item = sl.items.get(id=item_id)
        except (ShoppingList.DoesNotExist, ShoppingItem.DoesNotExist):
            return Response(status=status.HTTP_404_NOT_FOUND)

        if "checked" in request.data:
            item.checked = bool(request.data["checked"])
        if "quantity_note" in request.data:
            item.quantity_note = request.data["quantity_note"]
        item.save()
        return Response(ShoppingItemSerializer(item).data)


class ShoppingListShareView(APIView):
    """GET /v1/shopping-lists/<id>/share/ — WhatsApp-ready plain text."""

    permission_classes = [IsAuthenticated, RequiresPlus]

    @extend_schema(
        responses={200: {"type": "object", "properties": {"text": {"type": "string"}}}},
        summary="Get WhatsApp share text for a shopping list",
    )
    def get(self, request, list_id):
        try:
            sl = ShoppingList.objects.get(id=list_id, user=request.user)
        except ShoppingList.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        text = shopping_list_to_whatsapp(sl)
        return Response({"text": text})
