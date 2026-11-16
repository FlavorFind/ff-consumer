"""Search views — wraps engine search with pantry + diet injection."""

import logging

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.billing.entitlements import user_has_active_plus
from apps.engine_client.client import EngineUnavailableError
from apps.search.serializers import (
    IngredientQuerySerializer,
    ResolveRequestSerializer,
    SearchRequestSerializer,
)
from apps.search.services import (
    ALLERGEN_DISCLAIMER,
    ANONYMOUS_RESULT_LIMIT,
    FREE_RESULT_LIMIT,
    get_dish,
    get_ingredients,
    list_dishes,
    resolve,
    search,
)

logger = logging.getLogger(__name__)


class SearchView(APIView):
    """POST /v1/search/ — personalised recipe search.

    Automatically injects:
    - The user's pantry items
    - The user's diet tags and allergen exclusions (ALWAYS, non-negotiable)

    Returns tiered results: exact, can_make, almost (explore mode only).

    Public endpoint: unauthenticated callers get a restricted result set,
    authenticated free users the standard cap, Plus subscribers the maximum.
    """

    permission_classes = [AllowAny]

    class SearchThrottle(UserRateThrottle):
        scope = "user"

    throttle_classes = [SearchThrottle]

    def get_throttles(self):
        if self.request.user and self.request.user.is_authenticated:
            return [self.SearchThrottle()]
        return [AnonRateThrottle()]

    @extend_schema(
        request=SearchRequestSerializer,
        responses={200: {"type": "object"}},
        summary="Search for recipes",
        description=(
            "Search for recipes using your pantry and dietary preferences. "
            "Your pantry is injected automatically. "
            "Diet tags and allergen exclusions from your profile are ALWAYS applied. "
            "\n\n**Allergen disclaimer:** " + ALLERGEN_DISCLAIMER
        ),
    )
    def post(self, request):
        ser = SearchRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        limit = ser.validated_data["limit"]
        if not request.user.is_authenticated:
            limit = min(limit, ANONYMOUS_RESULT_LIMIT)
        elif not user_has_active_plus(request.user):
            limit = min(limit, FREE_RESULT_LIMIT)

        result = search(
            user=request.user,
            ingredients=ser.validated_data["ingredients"],
            mode=ser.validated_data["mode"],
            exclude=ser.validated_data["exclude"],
            lang=ser.validated_data["lang"],
            limit=limit,
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

        try:
            result = resolve(
                tokens=ser.validated_data["tokens"],
                lang=ser.validated_data["lang"],
            )
        except EngineUnavailableError:
            return Response(
                {
                    "engine_status": "degraded",
                    "results": [],
                    "ambiguous": [],
                    "unmatched": ser.validated_data["tokens"],
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(result)


class IngredientsView(APIView):
    """GET /v1/ingredients/ — autocomplete ingredient search.

    Results are cached for 10 minutes. Debounce on the client side.
    Open to all users — guests get autocomplete too.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[IngredientQuerySerializer],
        responses={200: {"type": "object"}},
        summary="Ingredient autocomplete",
        description="Fuzzy ingredient search for the autocomplete input. Cached 10 minutes.",
    )
    def get(self, request):
        ser = IngredientQuerySerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)

        try:
            result = get_ingredients(
                q=ser.validated_data["q"],
                lang=ser.validated_data["lang"],
            )
        except EngineUnavailableError:
            return Response(
                {"engine_status": "degraded", "results": []},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
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
        try:
            result = get_dish(slug=slug, lang=lang)
        except EngineUnavailableError:
            return Response(
                {"engine_status": "degraded", "slug": slug},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(result)


class DishListView(APIView):
    """GET /v1/dishes/ — dish catalogue from the engine.

    Query params:
        has_image (bool): if true, only return dishes with image_url set.
                          Used by Android/iOS for the home screen carousel.
        meal_type (str):  filter by meal type (breakfast, lunch, dinner, snack).
        limit (int):      max results to return (default 10, max 25).

    Public endpoint — no auth required.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: {"type": "object"}},
        summary="Dish catalogue",
        description=(
            "List dishes from the engine catalogue. "
            "Pass has_image=true to get only dishes with a Cloudinary image — "
            "used by the mobile app home screen carousel."
        ),
    )
    def get(self, request):
        raw_has_image = request.query_params.get("has_image", "").lower()
        has_image = True if raw_has_image in ("true", "1", "yes") else (
            False if raw_has_image in ("false", "0", "no") else None
        )
        meal_type = request.query_params.get("meal_type") or None
        try:
            limit = min(int(request.query_params.get("limit", 10)), 25)
        except (ValueError, TypeError):
            limit = 10

        try:
            result = list_dishes(has_image=has_image, meal_type=meal_type, limit=limit)
        except EngineUnavailableError:
            return Response(
                {"engine_status": "degraded", "count": 0, "results": []},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(result)
