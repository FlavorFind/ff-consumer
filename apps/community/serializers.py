"""Serializers for the community app."""

from rest_framework import serializers

from apps.community.models import Review, Submission

# Required fields for a community recipe submission
REQUIRED_SUBMISSION_FIELDS = ["name_en", "description", "ingredients", "steps"]


class SubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Submission
        fields = [
            "id",
            "payload",
            "status",
            "engine_submission_id",
            "reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "engine_submission_id", "reason", "created_at", "updated_at"]


class CreateSubmissionSerializer(serializers.Serializer):
    """Input for POST /v1/submissions/."""

    name_en = serializers.CharField(max_length=300)
    name_sw = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    description = serializers.CharField()
    # List of ingredient objects: {name: str, quantity: str}
    ingredients = serializers.ListField(
        child=serializers.DictField(), min_length=1, max_length=50
    )
    # List of step strings
    steps = serializers.ListField(
        child=serializers.CharField(), min_length=1, max_length=30
    )
    meal_type = serializers.ChoiceField(
        choices=["breakfast", "lunch", "dinner", "snack", "dessert", "drink", "any"],
        required=False,
        default="any",
    )
    region_slug = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ["id", "dish_id", "dish_slug", "stars", "text", "status", "created_at"]
        read_only_fields = ["id", "status", "created_at"]


class CreateReviewSerializer(serializers.Serializer):
    """Input for POST /v1/dishes/<slug>/reviews/."""

    stars = serializers.IntegerField(min_value=1, max_value=5)
    text = serializers.CharField(required=False, allow_blank=True, default="")
