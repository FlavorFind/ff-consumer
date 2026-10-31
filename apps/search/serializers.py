"""Serializers for the search app."""

from rest_framework import serializers


class SearchRequestSerializer(serializers.Serializer):
    """Input for POST /v1/search/."""

    ingredients = serializers.ListField(
        child=serializers.CharField(max_length=200),
        allow_empty=True,
        max_length=30,
        default=list,
        help_text="Ingredient names or slugs. Your pantry is always included automatically.",
    )
    mode = serializers.ChoiceField(
        choices=["strict", "explore"],
        default="strict",
        help_text=(
            "strict: only exact/can_make results. "
            "explore: also includes 'almost' results (1-2 missing ingredients)."
        ),
    )
    lang = serializers.ChoiceField(choices=["en", "sw"], default="en")
    limit = serializers.IntegerField(min_value=1, max_value=50, default=20)
    meal_type = serializers.ChoiceField(
        choices=["breakfast", "lunch", "dinner", "snack", "dessert", "drink", "any"],
        required=False,
        allow_null=True,
        default=None,
    )
    exclude = serializers.ListField(
        child=serializers.CharField(max_length=200),
        required=False,
        default=list,
        help_text="Ingredient slugs to exclude from results.",
    )


class ResolveRequestSerializer(serializers.Serializer):
    """Input for POST /v1/resolve/."""

    tokens = serializers.ListField(
        child=serializers.CharField(max_length=200),
        min_length=1,
        max_length=30,
        help_text="Free-text ingredient tokens to resolve (e.g. 'nyanya', 'unga').",
    )
    lang = serializers.ChoiceField(choices=["en", "sw"], default="en")


class IngredientQuerySerializer(serializers.Serializer):
    """Query params for GET /v1/ingredients/."""

    q = serializers.CharField(max_length=200, required=False, default="")
    lang = serializers.ChoiceField(choices=["en", "sw"], default="en")
