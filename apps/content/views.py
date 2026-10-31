"""Content views — regions and stories."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.content.models import Story


class StorySerializer(serializers.ModelSerializer):
    region_slug_list = serializers.SerializerMethodField()

    class Meta:
        model = Story
        fields = [
            "id",
            "slug",
            "title_en",
            "title_sw",
            "body_en",
            "body_sw",
            "region_slugs",
            "region_slug_list",
            "author",
            "published_at",
        ]

    def get_region_slug_list(self, obj) -> list[str]:
        return obj.get_region_slug_list()


class RegionsView(APIView):
    """GET /v1/regions/ — proxies engine regions list, cached 24 hours."""

    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: {"type": "object"}},
        summary="List regions (counties)",
        description="Returns all Kenyan counties and regions from the engine. Cached 24 hours.",
    )
    def get(self, request):
        from apps.engine_client.client import EngineUnavailableError, engine

        lang = request.query_params.get("lang", "en")
        try:
            result = engine.get_regions(lang=lang)
            return Response(result)
        except EngineUnavailableError:
            return Response(
                {"engine_status": "degraded", "regions": []},
                status=503,
            )


class StoryListView(APIView):
    """GET /v1/stories/ — list published editorial stories."""

    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: StorySerializer(many=True)},
        summary="List stories",
        description="List all published Taste of 47 Counties editorial stories.",
    )
    def get(self, request):
        stories = Story.objects.filter(status=Story.Status.PUBLISHED).order_by("-published_at")
        region = request.query_params.get("region")
        if region:
            stories = stories.filter(region_slugs__icontains=region)
        return Response(StorySerializer(stories, many=True).data)


class StoryDetailView(APIView):
    """GET /v1/stories/<slug>/ — single story."""

    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: StorySerializer},
        summary="Story detail",
    )
    def get(self, request, slug):
        try:
            story = Story.objects.get(slug=slug, status=Story.Status.PUBLISHED)
        except Story.DoesNotExist:
            return Response(status=404)
        return Response(StorySerializer(story).data)
