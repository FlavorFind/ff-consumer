"""Search views — wraps engine search with pantry + diet injection."""

import logging

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.search.serializers import (
    IngredientQuerySerializer,
    ResolveRequestSerializer,
    SearchRequestSerializer,
)
from apps.search.services import ALLERGEN_DISCLAIMER, get_dish, get_ingredients, resolve, search

logger = logging.getLogger(__name__)


class SearchView(APIView):
    """POST /v1/search/ — personalised recipe search.

    Automatically injects:
    - The user's pantry items
    - The user's diet tags and allergen exclusions (ALWAYS, non-negotiable)

    Returns tiered results: exact, can_make, almost (explore mode only).
    """

    permission_classes = [IsAuthenticated]

    class SearchThrottle(UserRateThrottle):
        scope = "user"

    throttle_classes = [SearchThrottle]

    @extend_schema(
        request=SearchRequestSerializer,
        responses={200: {"type": "object"}},
        summary="Search for recipes",
        description=(
            "Search for recipes using your pantry and dietary preferences. "
            "Your pantry is injected automatically. "
            "Diet tags and allergen exclusions from your profile are ALWAYS applied. "
            "\n\n**Allergen disclaimer:** "
            + ALLERGEN_DISCLAIMER
        ),
    )
    def post(self, request):
        ser = SearchRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        result = search(
            user=request.user,
            ingredients=ser.validated_data["ingredients"],
            mode=ser.validated_data["mode"],
            exclude=ser.validated_data["exclude"],
            lang=ser.validated_data["lang"],
            limit=ser.validated_data["limit"],
            meal_type=ser.validated_data["meal_type"],
        )

        return Response(result)


class ResolveView(APIView):
    """POST /v1/resolve/ — resolve free-text ingredient tokens to engine IDs.

    Must be called before search when the user types free text.
    If any token is ambiguous, the response includes choices for the user to pick from.
    NEVER pass an ambiguous token straight to search.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ResolveRequestSerializer,
        responses={200: {"type": "object"}},
        summary="Resolve ingredient tokens",
        description=(
            "Resolve free-text ingredient names to engine ingredient IDs. "
            "Handles Swahili, Sheng, misspellings, and aliases. "
            "If a token is ambiguous (e.g. 'unga' could be maize flour or wheat flour), "
            "the response includes choices — show them to the user, never guess."
        ),
    )
    def post(self, request):
        ser = ResolveRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        result = resolve(
            tokens=ser.validated_data["tokens"],
            lang=ser.validated_data["lang"],
        )
        return Response(result)


class IngredientsView(APIView):
    """GET /v1/ingredients/ — autocomplete ingredient search.

    Results are cached for 10 minutes. Debounce on the client side.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[IngredientQuerySerializer],
        responses={200: {"type": "object"}},
        summary="Ingredient autocomplete",
        description="Fuzzy ingredient search for the autocomplete input. Cached 10 minutes.",
    )
    def get(self, request):
        ser = IngredientQuerySerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)

        result = get_ingredients(
            q=ser.validated_data["q"],
            lang=ser.validated_data["lang"],
        )
        return Response(result)


class DishDetailView(APIView):
    """GET /v1/dishes/<slug>/ — engine dish detail proxy with ETag caching.

    Public endpoint — no auth required for basic dish info.
    Personalisation (missing ingredients, pairing suggestions) requires auth.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: {"type": "object"}},
        summary="Dish detail",
        description=(
            "Fetch full dish information from the engine. Cached per dataset version. "
            "\n\n**" + ALLERGEN_DISCLAIMER + "**"
        ),
    )
    def get(self, request, slug):
        lang = request.query_params.get("lang", "en")
        result = get_dish(slug=slug, lang=lang)
        return Response(result)
