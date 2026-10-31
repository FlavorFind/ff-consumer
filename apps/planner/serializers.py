"""Serializers for the planner app."""

from rest_framework import serializers

from apps.planner.models import MealPlan, MealPlanEntry, ShoppingItem, ShoppingList


class MealPlanEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = MealPlanEntry
        fields = ["id", "day", "meal_type", "dish_id", "dish_slug", "servings", "note", "position"]
        read_only_fields = ["id"]


class MealPlanSerializer(serializers.ModelSerializer):
    entries = MealPlanEntrySerializer(many=True, read_only=True)

    class Meta:
        model = MealPlan
        fields = ["id", "week_start", "entries", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class MealPlanWriteSerializer(serializers.Serializer):
    """Input for PUT /v1/plans/<week>/."""

    entries = MealPlanEntrySerializer(many=True)


class ShoppingItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShoppingItem
        fields = [
            "id",
            "ingredient_id",
            "ingredient_slug",
            "display_name",
            "quantity_note",
            "checked",
            "price_estimate_kes",
            "position",
        ]
        read_only_fields = ["id", "ingredient_id", "ingredient_slug", "display_name"]


class ShoppingListSerializer(serializers.ModelSerializer):
    items = ShoppingItemSerializer(many=True, read_only=True)

    class Meta:
        model = ShoppingList
        fields = ["id", "plan", "name", "items", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
