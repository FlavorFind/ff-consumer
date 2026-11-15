"""Serializers for the pantry app."""

import re

from rest_framework import serializers

from apps.pantry.models import PantryItem


class PantryItemSerializer(serializers.ModelSerializer):
    """Read-only pantry item representation."""

    class Meta:
        model = PantryItem
        fields = [
            "id",
            "ingredient_id",
            "ingredient_slug",
            "display_name",
            "added_at",
            "expires_on",
        ]
        read_only_fields = fields


class AddPantryItemSerializer(serializers.Serializer):
    """Add an ingredient to the pantry by engine ingredient id or slug."""

    ingredient_id = serializers.CharField(max_length=36, required=False, allow_null=True)
    ingredient_slug = serializers.CharField(max_length=200, required=False, allow_blank=True)
    display_name = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    expires_on = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        ingredient_id = attrs.get("ingredient_id")
        ingredient_slug = attrs.get("ingredient_slug") or ""
        if not ingredient_id and not ingredient_slug:
            raise serializers.ValidationError(
                "Either ingredient_id or ingredient_slug is required."
            )
        if ingredient_id:
            # Basic UUID format check — engine IDs are UUIDs
            uuid_pattern = re.compile(
                r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                re.IGNORECASE,
            )
            if not uuid_pattern.match(ingredient_id):
                raise serializers.ValidationError("ingredient_id must be a valid UUID.")
        return attrs
