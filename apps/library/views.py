"""Library views — saved recipes, collections, cooking history."""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.entitlements import FREE_SAVE_LIMIT, user_has_active_plus
from apps.library.models import Collection, CookLog, SavedRecipe
from apps.library.serializers import (
    CollectionSerializer,
    CookLogSerializer,
    LogCookSerializer,
    SavedRecipeSerializer,
    SaveRecipeSerializer,
)


class SavedRecipeListView(APIView):
    """List and save recipes. Free tier: max 20. Plus: unlimited."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: SavedRecipeSerializer(many=True)},
        summary="List saved recipes",
    )
    def get(self, request):
        recipes = SavedRecipe.objects.filter(user=request.user).select_related("collection")
        return Response(SavedRecipeSerializer(recipes, many=True).data)

    @extend_schema(
        request=SaveRecipeSerializer,
        responses={201: SavedRecipeSerializer},
        summary="Save a recipe",
        description=(
            "Save a dish from the engine. Free tier: up to 20 saved recipes. " "Plus: unlimited."
        ),
    )
    def post(self, request):
        ser = SaveRecipeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        # Enforce free tier limit
        if not user_has_active_plus(request.user):
            count = SavedRecipe.objects.filter(user=request.user).count()
            if count >= FREE_SAVE_LIMIT:
                return Response(
                    {
                        "error": {
                            "code": "save_limit_reached",
                            "message": (
                                f"Free tier allows up to {FREE_SAVE_LIMIT} saved recipes. "
                                "Upgrade to Flavor Find Plus for unlimited saves."
                            ),
                        }
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Get current dataset version for drift detection
        from apps.engine_client.client import engine

        dataset_version = engine.get_dataset_version()

        collection = None
        if ser.validated_data.get("collection_id"):
            try:
                collection = Collection.objects.get(
                    id=ser.validated_data["collection_id"],
                    user=request.user,
                )
            except Collection.DoesNotExist:
                return Response(
                    {"error": {"code": "not_found", "message": "Collection not found."}},
                    status=status.HTTP_404_NOT_FOUND,
                )

        recipe, created = SavedRecipe.objects.update_or_create(
            user=request.user,
            dish_id=ser.validated_data["dish_id"],
            defaults={
                "dish_slug": ser.validated_data["dish_slug"],
                "dataset_version": dataset_version,
                "collection": collection,
                "note": ser.validated_data.get("note", ""),
            },
        )

        return Response(
            SavedRecipeSerializer(recipe).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class SavedRecipeDetailView(APIView):
    """Update note/collection or unsave a recipe."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=SaveRecipeSerializer,
        responses={200: SavedRecipeSerializer},
        summary="Update a saved recipe",
    )
    def patch(self, request, recipe_id):
        try:
            recipe = SavedRecipe.objects.get(id=recipe_id, user=request.user)
        except SavedRecipe.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if "note" in request.data:
            recipe.note = request.data["note"]
        if "collection_id" in request.data:
            cid = request.data["collection_id"]
            if cid is None:
                recipe.collection = None
            else:
                try:
                    recipe.collection = Collection.objects.get(id=cid, user=request.user)
                except Collection.DoesNotExist:
                    return Response(
                        {"error": {"code": "not_found", "message": "Collection not found."}},
                        status=status.HTTP_404_NOT_FOUND,
                    )
        recipe.save()
        return Response(SavedRecipeSerializer(recipe).data)

    @extend_schema(responses={204: None}, summary="Unsave a recipe")
    def delete(self, request, recipe_id):
        try:
            recipe = SavedRecipe.objects.get(id=recipe_id, user=request.user)
        except SavedRecipe.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        recipe.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CollectionListView(APIView):
    """List and create collections."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: CollectionSerializer(many=True)}, summary="List collections")
    def get(self, request):
        cols = Collection.objects.filter(user=request.user)
        return Response(CollectionSerializer(cols, many=True).data)

    @extend_schema(
        request=CollectionSerializer,
        responses={201: CollectionSerializer},
        summary="Create a collection",
    )
    def post(self, request):
        ser = CollectionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        col, created = Collection.objects.get_or_create(
            user=request.user,
            name=ser.validated_data["name"],
        )
        return Response(
            CollectionSerializer(col).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class CollectionDetailView(APIView):
    """Rename or delete a collection."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=CollectionSerializer,
        responses={200: CollectionSerializer},
        summary="Rename a collection",
    )
    def patch(self, request, col_id):
        try:
            col = Collection.objects.get(id=col_id, user=request.user)
        except Collection.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if "name" in request.data:
            col.name = request.data["name"]
            col.save(update_fields=["name", "updated_at"])
        return Response(CollectionSerializer(col).data)

    @extend_schema(responses={204: None}, summary="Delete a collection")
    def delete(self, request, col_id):
        try:
            col = Collection.objects.get(id=col_id, user=request.user)
        except Collection.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        col.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CookLogListView(APIView):
    """List and log cooked dishes."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: CookLogSerializer(many=True)}, summary="List cooking history")
    def get(self, request):
        logs = CookLog.objects.filter(user=request.user)
        return Response(CookLogSerializer(logs, many=True).data)

    @extend_schema(
        request=LogCookSerializer,
        responses={201: CookLogSerializer},
        summary="Log a cooked dish",
    )
    def post(self, request):
        ser = LogCookSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        log = CookLog.objects.create(
            user=request.user,
            dish_id=ser.validated_data["dish_id"],
            dish_slug=ser.validated_data["dish_slug"],
            rating=ser.validated_data.get("rating"),
            note=ser.validated_data.get("note", ""),
        )
        return Response(CookLogSerializer(log).data, status=status.HTTP_201_CREATED)
