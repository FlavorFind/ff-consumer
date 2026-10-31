"""Health and meta views for the consumer API."""

import logging

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class HealthView(APIView):
    """Health check — no auth required."""

    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: {"type": "object"}},
        summary="Health check",
        description="Returns the health status of the consumer API.",
    )
    def get(self, request):
        return Response(
            {
                "status": "ok",
                "service": "ff-consumer",
                "version": getattr(settings, "CONSUMER_VERSION", "dev"),
            }
        )


class MetaVersionView(APIView):
    """Returns consumer version + engine dataset version — no auth required."""

    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: {"type": "object"}},
        summary="API and dataset version",
        description=(
            "Returns the consumer backend version and the current engine dataset version. "
            "The dataset_version changes when food data is updated in the engine."
        ),
    )
    def get(self, request):
        from apps.engine_client.client import engine

        engine_status = "ok"
        dataset_version = "unknown"
        engine_version = "unknown"

        try:
            data = engine.get_version()
            dataset_version = data.get("dataset_version", "unknown")
            engine_version = data.get("engine_version", "unknown")
        except Exception as exc:
            logger.warning("Could not fetch engine version: %s", exc)
            engine_status = "degraded"
            # Read the cached dataset version without making another network call
            from django.core.cache import cache

            dataset_version = cache.get("ffconsumer:engine:dataset_version", "unknown")

        return Response(
            {
                "consumer_version": getattr(settings, "CONSUMER_VERSION", "dev"),
                "engine_version": engine_version,
                "dataset_version": dataset_version,
                "engine_status": engine_status,
            }
        )
