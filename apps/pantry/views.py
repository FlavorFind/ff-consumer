"""Pantry views — CRUD for pantry items + can-make summary."""

import uuid

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.pantry.models import PantryItem
from apps.pantry.serializers import (
    AddPantryItemSerializer,
    PantryItemSerializer,
    PatchPantryItemSerializer,
)


class PantryView(APIView):
    """List and add pantry items."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: PantryItemSerializer(many=True)},
        summary="List pantry items",
        description="Returns all ingredients in the current user's pantry.",
    )
    def get(self, request):
        items = PantryItem.objects.filter(user=request.user)
        return Response(PantryItemSerializer(items, many=True).data)

    @extend_schema(
        request=AddPantryItemSerializer,
        responses={201: PantryItemSerializer},
        summary="Add item to pantry",
        description=(
            "Add an ingredient to the pantry. Optionally include quantity, unit, "
            "low_stock_threshold, and expires_on. Use /v1/ingredients/ to look up "
            "ingredient_id and ingredient_slug from the engine first."
        ),
    )
    def post(self, request):
        ser = AddPantryItemSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        ingredient_id = ser.validated_data.get("ingredient_id") or str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"flavorfind:pantry:{ser.validated_data.get('ingredient_slug') or ''}",
            )
        )
        ingredient_slug = ser.validated_data.get("ingredient_slug") or ingredient_id
        display_name = ser.validated_data.get("display_name") or ingredient_slug

        defaults = {
            "ingredient_slug": ingredient_slug,
            "display_name": display_name,
            "expires_on": ser.validated_data.get("expires_on"),
        }
        # Only include optional quantity fields if provided
        if ser.validated_data.get("quantity") is not None:
            defaults["quantity"] = ser.validated_data["quantity"]
        if ser.validated_data.get("unit"):
            defaults["unit"] = ser.validated_data["unit"]
        if ser.validated_data.get("low_stock_threshold") is not None:
            defaults["low_stock_threshold"] = ser.validated_data["low_stock_threshold"]

        item, created = PantryItem.objects.get_or_create(
            user=request.user,
            ingredient_id=ingredient_id,
            defaults=defaults,
        )

        if not created:
            # Update all writable fields on re-add
            update_fields = ["ingredient_slug", "display_name", "expires_on"]
            item.ingredient_slug = ser.validated_data.get("ingredient_slug") or item.ingredient_slug
            item.display_name = ser.validated_data.get("display_name") or item.display_name
            item.expires_on = ser.validated_data.get("expires_on")
            if ser.validated_data.get("quantity") is not None:
                item.quantity = ser.validated_data["quantity"]
                update_fields.append("quantity")
            if ser.validated_data.get("unit"):
                item.unit = ser.validated_data["unit"]
                update_fields.append("unit")
            if "low_stock_threshold" in ser.validated_data:
                item.low_stock_threshold = ser.validated_data["low_stock_threshold"]
                update_fields.append("low_stock_threshold")
            item.save(update_fields=update_fields)

        return Response(
            PantryItemSerializer(item).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PantryItemDetailView(APIView):
    """PATCH and DELETE a single pantry item."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=PatchPantryItemSerializer,
        responses={200: PantryItemSerializer},
        summary="Update pantry item quantity, unit, threshold, or expiry",
        description=(
            "Partial update — only send the fields you want to change. "
            "Set quantity=null to remove quantity tracking."
        ),
    )
    def patch(self, request, item_id):
        try:
            item = PantryItem.objects.get(id=item_id, user=request.user)
        except PantryItem.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        ser = PatchPantryItemSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        update_fields = []
        if "quantity" in ser.validated_data:
            item.quantity = ser.validated_data["quantity"]
            update_fields.append("quantity")
        if "unit" in ser.validated_data:
            item.unit = ser.validated_data["unit"]
            update_fields.append("unit")
        if "low_stock_threshold" in ser.validated_data:
            item.low_stock_threshold = ser.validated_data["low_stock_threshold"]
            update_fields.append("low_stock_threshold")
        if "expires_on" in ser.validated_data:
            item.expires_on = ser.validated_data["expires_on"]
            update_fields.append("expires_on")

        if update_fields:
            item.save(update_fields=update_fields)

        # Fire low-stock check immediately after any quantity update
        if "quantity" in update_fields:
            from apps.pantry.tasks import check_single_item_low_stock
            check_single_item_low_stock.delay(str(item.id))

        return Response(PantryItemSerializer(item).data)

    @extend_schema(responses={204: None}, summary="Remove item from pantry")
    def delete(self, request, item_id):
        try:
            item = PantryItem.objects.get(id=item_id, user=request.user)
        except PantryItem.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PantryCanMakeView(APIView):
    """GET /v1/pantry/can-make/ — dishes the user can cook from their pantry.

    Uses the pantry ingredient slugs to call the engine search endpoint.
    Returns a summary (total count + breakdown by meal type) plus up to 50 dishes.

    This is a Plus feature — it uses the full ingredient list which can be large.
    Free users get a capped count only.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: {"type": "object"}},
        summary="Dishes I can make from my pantry",
        description=(
            "Returns dishes the user can cook using their current pantry. "
            "Grouped by meal type. Full dish list requires Plus."
        ),
    )
    def get(self, request):
        from apps.billing.entitlements import user_has_active_plus
        from apps.engine_client.client import EngineUnavailableError, engine

        pantry_items = PantryItem.objects.filter(user=request.user).values_list(
            "ingredient_slug", flat=True
        )
        slugs = list(pantry_items)

        if not slugs:
            return Response(
                {
                    "count": 0,
                    "by_meal_type": {},
                    "dishes": [],
                    "message": "Add ingredients to your pantry to see what you can cook.",
                }
            )

        is_plus = user_has_active_plus(request.user)

        try:
            result = engine.search(
                ingredients=slugs,
                mode="explore",
                limit=50,
            )
        except EngineUnavailableError:
            return Response(
                {"error": {"code": "engine_unavailable", "message": "Recipe engine is temporarily unavailable."}},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Flatten all tiers
        all_dishes = (
            result.get("results", {}).get("exact", [])
            + result.get("results", {}).get("can_make", [])
            + result.get("results", {}).get("almost", [])
        )

        # Group by meal_type
        by_meal_type: dict[str, list] = {}
        for dish in all_dishes:
            meal = dish.get("meal_type") or "other"
            by_meal_type.setdefault(meal, []).append({
                "slug": dish.get("slug", ""),
                "name_en": dish.get("name_en", ""),
                "name_sw": dish.get("name_sw", ""),
                "image_url": dish.get("image_url"),
                "tier": dish.get("tier", ""),
                "score": dish.get("score", 0),
                "missing_count": len(dish.get("missing", [])),
            })

        meal_type_counts = {k: len(v) for k, v in by_meal_type.items()}
        total = len(all_dishes)

        # Free users get the count only — no dish details
        if not is_plus:
            return Response(
                {
                    "count": total,
                    "by_meal_type": meal_type_counts,
                    "dishes": [],
                    "plus_required": True,
                    "message": (
                        f"You can make {total} dishes with what's in your pantry. "
                        "Subscribe to Plus to see them all."
                    ),
                }
            )

        return Response(
            {
                "count": total,
                "by_meal_type": meal_type_counts,
                "dishes": by_meal_type,
                "plus_required": False,
            }
        )
