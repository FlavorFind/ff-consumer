"""Profile views for ff-consumer."""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.profiles.models import Profile, ProfileDiet
from apps.profiles.serializers import (
    ProfileDietSerializer,
    ProfileDietUpdateSerializer,
    ProfileSerializer,
)


class ProfileView(APIView):
    """GET and PATCH the current user's profile."""

    permission_classes = [IsAuthenticated]

    def _get_or_create_profile(self, user):
        profile, _ = Profile.objects.get_or_create(user=user)
        return profile

    @extend_schema(responses={200: ProfileSerializer}, summary="Get profile")
    def get(self, request):
        profile = self._get_or_create_profile(request.user)
        return Response(ProfileSerializer(profile).data)

    @extend_schema(
        request=ProfileSerializer, responses={200: ProfileSerializer}, summary="Update profile"
    )
    def patch(self, request):
        profile = self._get_or_create_profile(request.user)
        serializer = ProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ProfileDietView(APIView):
    """GET and PATCH the current user's diet tags."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: ProfileDietSerializer(many=True)},
        summary="Get diet tags",
    )
    def get(self, request):
        tags = ProfileDiet.objects.filter(user=request.user)
        return Response(ProfileDietSerializer(tags, many=True).data)

    @extend_schema(
        request=ProfileDietUpdateSerializer,
        responses={200: ProfileDietSerializer(many=True)},
        summary="Replace diet tags",
        description=(
            "Replaces the full set of diet tags. "
            "Allergen tags (source=allergen) are always included on engine search calls. "
            "**Allergen information is for guidance only. Always confirm with the kitchen.**"
        ),
    )
    def patch(self, request):
        serializer = ProfileDietUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_slugs = set(serializer.validated_data["diet_tags"])

        # Remove tags no longer in the list
        ProfileDiet.objects.filter(user=request.user).exclude(diet_tag_slug__in=new_slugs).delete()

        # Add new tags
        existing = set(
            ProfileDiet.objects.filter(user=request.user).values_list("diet_tag_slug", flat=True)
        )
        to_create = [
            ProfileDiet(user=request.user, diet_tag_slug=slug) for slug in new_slugs - existing
        ]
        if to_create:
            ProfileDiet.objects.bulk_create(to_create)

        tags = ProfileDiet.objects.filter(user=request.user)
        return Response(ProfileDietSerializer(tags, many=True).data)
