"""Serializers for the library app."""

from rest_framework import serializers

from apps.library.models import Collection, CookLog, SavedRecipe


class CollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collection
        fields = ["id", "name", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class SavedRecipeSerializer(serializers.ModelSerializer):
    collection_name = serializers.CharField(
        source="collection.name", read_only=True, allow_null=True
    )

    class Meta:
        model = SavedRecipe
        fields = [
            "id",
            "dish_id",
            "dish_slug",
            "dataset_version",
            "collection",
            "collection_name",
            "note",
            "saved_at",
        ]
        read_only_fields = ["id", "saved_at", "dataset_version"]


class SaveRecipeSerializer(serializers.Serializer):
    """Input for saving a recipe."""

    dish_id = serializers.CharField(max_length=36)
    dish_slug = serializers.CharField(max_length=200)
    collection_id = serializers.UUIDField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class CookLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = CookLog
        fields = ["id", "dish_id", "dish_slug", "cooked_at", "rating", "note"]
        read_only_fields = ["id", "cooked_at"]


class LogCookSerializer(serializers.Serializer):
    """Input for logging a cooked dish."""

    dish_id = serializers.CharField(max_length=36)
    dish_slug = serializers.CharField(max_length=200)
    rating = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")
