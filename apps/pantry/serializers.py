"""Serializers for the pantry app."""

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
    """Add an ingredient to the pantry by providing engine ingredient details."""

    ingredient_id = serializers.CharField(max_length=36)
    ingredient_slug = serializers.CharField(max_length=200)
    display_name = serializers.CharField(max_length=200)
    expires_on = serializers.DateField(required=False, allow_null=True)

    def validate_ingredient_id(self, value):
        # Basic UUID format check — engine IDs are UUIDs
        import re
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )
        if not uuid_pattern.match(value):
            raise serializers.ValidationError("ingredient_id must be a valid UUID.")
        return value
