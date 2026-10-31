"""Pantry views — CRUD for pantry items."""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.pantry.models import PantryItem
from apps.pantry.serializers import AddPantryItemSerializer, PantryItemSerializer


class PantryView(APIView):
    """List and add pantry items."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: PantryItemSerializer(many=True)},
        summary="List pantry items",
        description="Returns all ingredients in the current user's pantry.",
    )
    def get(self, request):
        items = PantryItem.objects.filter(user=request.user)
        return Response(PantryItemSerializer(items, many=True).data)

    @extend_schema(
        request=AddPantryItemSerializer,
        responses={201: PantryItemSerializer},
        summary="Add item to pantry",
        description=(
            "Add an ingredient to the pantry. Use /v1/ingredients/ to resolve "
            "the ingredient_id and ingredient_slug from the engine first."
        ),
    )
    def post(self, request):
        ser = AddPantryItemSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        item, created = PantryItem.objects.get_or_create(
            user=request.user,
            ingredient_id=ser.validated_data["ingredient_id"],
            defaults={
                "ingredient_slug": ser.validated_data["ingredient_slug"],
                "display_name": ser.validated_data["display_name"],
                "expires_on": ser.validated_data.get("expires_on"),
            },
        )

        if not created:
            # Update display name and expiry in case they changed
            item.ingredient_slug = ser.validated_data["ingredient_slug"]
            item.display_name = ser.validated_data["display_name"]
            item.expires_on = ser.validated_data.get("expires_on")
            item.save(update_fields=["ingredient_slug", "display_name", "expires_on"])

        return Response(
            PantryItemSerializer(item).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PantryItemDetailView(APIView):
    """Delete a single pantry item."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={204: None}, summary="Remove item from pantry")
    def delete(self, request, item_id):
        try:
            item = PantryItem.objects.get(id=item_id, user=request.user)
        except PantryItem.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
