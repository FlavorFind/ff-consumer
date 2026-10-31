"""Serializers for the profiles app."""

from rest_framework import serializers

from apps.profiles.models import Profile, ProfileDiet


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["household_size", "region_slug", "budget_kes_per_meal", "updated_at"]
        read_only_fields = ["updated_at"]


class ProfileDietSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfileDiet
        fields = ["diet_tag_slug", "source", "created_at"]
        read_only_fields = ["created_at"]


class ProfileDietUpdateSerializer(serializers.Serializer):
    """Replaces the user's full diet tag list."""

    diet_tags = serializers.ListField(
        child=serializers.CharField(max_length=100),
        help_text="List of engine dietary tag slugs (e.g. 'vegetarian', 'nut-free').",
    )
