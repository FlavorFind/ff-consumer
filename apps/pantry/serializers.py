"""Serializers for the pantry app."""

import re

from rest_framework import serializers

from apps.pantry.models import UNIT_CHOICES, PantryItem


class PantryItemSerializer(serializers.ModelSerializer):
    """Full pantry item representation — includes quantity tracking fields."""

    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = PantryItem
        fields = [
            "id",
            "ingredient_id",
            "ingredient_slug",
            "display_name",
            "quantity",
            "unit",
            "low_stock_threshold",
            "is_low_stock",
            "added_at",
            "expires_on",
        ]
        read_only_fields = ["id", "ingredient_id", "ingredient_slug", "added_at", "is_low_stock"]


class AddPantryItemSerializer(serializers.Serializer):
    """Add or update an ingredient in the pantry."""

    ingredient_id = serializers.CharField(max_length=36, required=False, allow_null=True)
    ingredient_slug = serializers.CharField(max_length=200, required=False, allow_blank=True)
    display_name = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    expires_on = serializers.DateField(required=False, allow_null=True)
    quantity = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True,
        help_text="How much the user currently has. Null = unknown.",
    )
    unit = serializers.ChoiceField(
        choices=[c[0] for c in UNIT_CHOICES] + [""],
        required=False, allow_blank=True, default="",
        help_text="Unit for quantity. Required when quantity is provided.",
    )
    low_stock_threshold = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True,
        help_text="Alert when quantity drops to this level. Null = no alert.",
    )

    def validate(self, attrs):
        ingredient_id = attrs.get("ingredient_id")
        ingredient_slug = attrs.get("ingredient_slug") or ""
        if not ingredient_id and not ingredient_slug:
            raise serializers.ValidationError(
                "Either ingredient_id or ingredient_slug is required."
            )
        if ingredient_id:
            uuid_pattern = re.compile(
                r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                re.IGNORECASE,
            )
            if not uuid_pattern.match(ingredient_id):
                raise serializers.ValidationError("ingredient_id must be a valid UUID.")
        quantity = attrs.get("quantity")
        unit = attrs.get("unit", "")
        if quantity is not None and not unit:
            raise serializers.ValidationError(
                "unit is required when quantity is provided."
            )
        return attrs


class PatchPantryItemSerializer(serializers.Serializer):
    """Patch quantity, unit, low_stock_threshold, or expires_on on an existing item."""

    quantity = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True,
    )
    unit = serializers.ChoiceField(
        choices=[c[0] for c in UNIT_CHOICES] + [""],
        required=False, allow_blank=True,
    )
    low_stock_threshold = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True,
    )
    expires_on = serializers.DateField(required=False, allow_null=True)
