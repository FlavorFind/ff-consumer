"""Sync views — offline change queue for Android app.

POST /v1/sync/push/ — client sends unsynced changes; server applies them
GET  /v1/sync/pull/?since= — server returns changes since last sync

Conflict rules:
- Server wins for shared data (plans, shopping lists)
- User wins for pantry and personal notes
- Last-write-wins for profile fields
"""

import logging
from datetime import UTC, datetime

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.entitlements import RequiresPlus

logger = logging.getLogger(__name__)


class ChangeSerializer(serializers.Serializer):
    """A single change from the client."""

    change_id = serializers.UUIDField()
    changed_at = serializers.DateTimeField()
    entity_type = serializers.ChoiceField(
        choices=["pantry_item", "saved_recipe", "cook_log", "meal_plan_entry", "shopping_item"]
    )
    entity_id = serializers.UUIDField()
    operation = serializers.ChoiceField(choices=["create", "update", "delete"])
    payload = serializers.DictField(required=False, default=dict)


class SyncPushSerializer(serializers.Serializer):
    changes = serializers.ListField(child=ChangeSerializer(), max_length=500)


class SyncPushView(APIView):
    """POST /v1/sync/push/ — apply offline changes from client.

    Requires Plus (offline sync is a Plus feature).
    """

    permission_classes = [IsAuthenticated, RequiresPlus]

    @extend_schema(
        request=SyncPushSerializer,
        responses={200: {"type": "object"}},
        summary="Push offline changes",
        description=(
            "Apply changes made offline to the server. "
            "Returns applied change IDs and any conflicts. Requires Plus."
        ),
    )
    def post(self, request):
        ser = SyncPushSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        changes = ser.validated_data["changes"]
        applied = []
        conflicts = []

        for change in changes:
            try:
                _apply_change(request.user, change)
                applied.append(str(change["change_id"]))
            except Exception as exc:
                logger.warning("Sync conflict for change %s: %s", change["change_id"], exc)
                conflicts.append({"change_id": str(change["change_id"]), "reason": str(exc)})

        # Update last_sync_at on the device
        _update_device_sync(request)

        return Response(
            {
                "applied": applied,
                "conflicts": conflicts,
                "server_time": timezone.now().isoformat(),
            }
        )


class SyncPullView(APIView):
    """GET /v1/sync/pull/?since=<ISO timestamp> — pull server-side changes.

    Requires Plus.
    """

    permission_classes = [IsAuthenticated, RequiresPlus]

    @extend_schema(
        responses={200: {"type": "object"}},
        summary="Pull server changes since last sync",
        description="Returns server-side changes since the given ISO timestamp. Requires Plus.",
    )
    def get(self, request):
        since_str = request.query_params.get("since")
        if since_str:
            try:
                since = datetime.fromisoformat(since_str.replace("Z", "+00:00"))
                since = timezone.make_aware(since) if timezone.is_naive(since) else since
            except ValueError:
                return Response(
                    {"error": {"code": "bad_request", "message": "Invalid 'since' timestamp."}},
                    status=400,
                )
        else:
            # First sync — return everything
            since = datetime(2000, 1, 1, tzinfo=UTC)

        user = request.user
        changes = _collect_changes_since(user, since)

        # Update last_sync_at
        _update_device_sync(request)

        return Response(
            {
                "changes": changes,
                "server_time": timezone.now().isoformat(),
                "count": len(changes),
            }
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _apply_change(user, change: dict):
    """Apply a single change from the client to the server."""
    entity_type = change["entity_type"]
    entity_id = str(change["entity_id"])
    operation = change["operation"]
    payload = change.get("payload", {})

    if entity_type == "pantry_item":
        _apply_pantry_change(user, entity_id, operation, payload)
    elif entity_type == "saved_recipe":
        _apply_saved_recipe_change(user, entity_id, operation, payload)
    elif entity_type == "cook_log":
        _apply_cook_log_change(user, entity_id, operation, payload)
    elif entity_type == "shopping_item":
        _apply_shopping_item_change(user, entity_id, operation, payload)
    # meal_plan_entry: server wins — ignore client changes to plan entries


def _apply_pantry_change(user, entity_id: str, operation: str, payload: dict):
    from apps.pantry.models import PantryItem

    if operation == "delete":
        PantryItem.objects.filter(id=entity_id, user=user).delete()
    elif operation in ("create", "update"):
        PantryItem.objects.update_or_create(
            id=entity_id,
            user=user,
            defaults={
                "ingredient_id": payload.get("ingredient_id", ""),
                "ingredient_slug": payload.get("ingredient_slug", ""),
                "display_name": payload.get("display_name", ""),
                "expires_on": payload.get("expires_on"),
            },
        )


def _apply_saved_recipe_change(user, entity_id: str, operation: str, payload: dict):
    from apps.library.models import SavedRecipe

    if operation == "delete":
        SavedRecipe.objects.filter(id=entity_id, user=user).delete()
    elif operation in ("create", "update"):
        from apps.engine_client.client import engine

        dataset_version = engine.get_dataset_version()
        SavedRecipe.objects.update_or_create(
            id=entity_id,
            user=user,
            defaults={
                "dish_id": payload.get("dish_id", ""),
                "dish_slug": payload.get("dish_slug", ""),
                "dataset_version": dataset_version,
                "note": payload.get("note", ""),
            },
        )


def _apply_cook_log_change(user, entity_id: str, operation: str, payload: dict):
    from apps.library.models import CookLog

    if operation == "delete":
        CookLog.objects.filter(id=entity_id, user=user).delete()
    elif operation in ("create", "update"):
        CookLog.objects.update_or_create(
            id=entity_id,
            user=user,
            defaults={
                "dish_id": payload.get("dish_id", ""),
                "dish_slug": payload.get("dish_slug", ""),
                "rating": payload.get("rating"),
                "note": payload.get("note", ""),
            },
        )


def _apply_shopping_item_change(user, entity_id: str, operation: str, payload: dict):
    from apps.planner.models import ShoppingItem

    if operation == "delete":
        ShoppingItem.objects.filter(id=entity_id, shopping_list__user=user).delete()
    elif operation == "update":
        # Only allow checking/unchecking — user wins here
        ShoppingItem.objects.filter(id=entity_id, shopping_list__user=user).update(
            checked=payload.get("checked", False)
        )


def _collect_changes_since(user, since) -> list[dict]:
    """Return all user data changes since `since` for the pull endpoint."""
    changes = []

    from apps.library.models import CookLog, SavedRecipe
    from apps.pantry.models import PantryItem

    for item in PantryItem.objects.filter(user=user, added_at__gt=since):
        changes.append(
            {
                "entity_type": "pantry_item",
                "entity_id": str(item.id),
                "operation": "create",
                "changed_at": item.added_at.isoformat(),
                "payload": {
                    "ingredient_id": item.ingredient_id,
                    "ingredient_slug": item.ingredient_slug,
                    "display_name": item.display_name,
                    "expires_on": item.expires_on.isoformat() if item.expires_on else None,
                },
            }
        )

    for recipe in SavedRecipe.objects.filter(user=user, saved_at__gt=since):
        changes.append(
            {
                "entity_type": "saved_recipe",
                "entity_id": str(recipe.id),
                "operation": "create",
                "changed_at": recipe.saved_at.isoformat(),
                "payload": {
                    "dish_id": recipe.dish_id,
                    "dish_slug": recipe.dish_slug,
                    "note": recipe.note,
                },
            }
        )

    for log in CookLog.objects.filter(user=user, cooked_at__gt=since):
        changes.append(
            {
                "entity_type": "cook_log",
                "entity_id": str(log.id),
                "operation": "create",
                "changed_at": log.cooked_at.isoformat(),
                "payload": {
                    "dish_id": log.dish_id,
                    "dish_slug": log.dish_slug,
                    "rating": log.rating,
                    "note": log.note,
                },
            }
        )

    return changes


def _update_device_sync(request):
    """Update last_sync_at on the device making the sync request."""
    # Device is identified by Authorization token — best effort
    try:
        from apps.accounts.models import Device

        user_agent = request.META.get("HTTP_USER_AGENT", "")
        platform = "android" if "Android" in user_agent else "web"
        Device.objects.filter(user=request.user, platform=platform).update(
            last_sync_at=timezone.now()
        )
    except Exception:
        pass  # Not critical — don't fail the sync
