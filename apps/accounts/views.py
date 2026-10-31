"""Auth views for ff-consumer."""

import logging

from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.serializers import (
    OTPRequestSerializer,
    OTPVerifySerializer,
    RegisterSerializer,
    TokenResponseSerializer,
    UserSerializer,
)
from apps.accounts.services import get_tokens_for_user, request_otp, verify_otp

logger = logging.getLogger(__name__)

User = get_user_model()


class RegisterView(APIView):
    """Register a new user with email and password."""

    permission_classes = [AllowAny]

    @extend_schema(
        request=RegisterSerializer,
        responses={201: TokenResponseSerializer},
        summary="Register with email and password",
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        tokens = get_tokens_for_user(user)
        return Response(
            {**tokens, "user": UserSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )


class OTPRequestView(APIView):
    """Request a phone OTP — step 1 of phone login."""

    permission_classes = [AllowAny]

    class OTPThrottle(ScopedRateThrottle):
        scope = "otp"

    throttle_classes = [OTPThrottle]

    @extend_schema(
        request=OTPRequestSerializer,
        responses={200: {"type": "object", "properties": {"detail": {"type": "string"}}}},
        summary="Request phone OTP",
    )
    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]
        try:
            request_otp(phone)
        except ValueError as exc:
            return Response(
                {"error": {"code": "otp_rate_limit", "message": str(exc)}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        return Response({"detail": "Verification code sent."})


class OTPVerifyView(APIView):
    """Verify the OTP and return JWT tokens — step 2 of phone login."""

    permission_classes = [AllowAny]

    class OTPThrottle(ScopedRateThrottle):
        scope = "otp"

    throttle_classes = [OTPThrottle]

    @extend_schema(
        request=OTPVerifySerializer,
        responses={200: TokenResponseSerializer},
        summary="Verify phone OTP and get tokens",
    )
    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = verify_otp(
                serializer.validated_data["phone"],
                serializer.validated_data["code"],
            )
        except ValueError as exc:
            return Response(
                {"error": {"code": "otp_invalid", "message": str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tokens = get_tokens_for_user(user)
        return Response({**tokens, "user": UserSerializer(user).data})


class _LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class LogoutView(APIView):
    """Revoke the refresh token — effectively logs the user out."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=_LogoutRequestSerializer,
        responses={204: None},
        summary="Logout and revoke refresh token",
    )
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": {"code": "bad_request", "message": "refresh token required"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            pass  # already invalid — still return 204
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """Current user's profile."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: UserSerializer}, summary="Get current user")
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class DeviceView(APIView):
    """Register a device for push notifications and sync tracking."""

    permission_classes = [IsAuthenticated]

    class _DeviceSerializer(serializers.Serializer):
        platform = serializers.ChoiceField(choices=["android", "ios", "web"])
        push_token = serializers.CharField(required=False, allow_blank=True, default="")

    class _DeviceResponseSerializer(serializers.Serializer):
        id = serializers.UUIDField()
        platform = serializers.CharField()
        push_token = serializers.CharField()
        created_at = serializers.DateTimeField()

    @extend_schema(
        request=_DeviceSerializer,
        responses={201: _DeviceResponseSerializer},
        summary="Register a device",
        description="Register a device to receive push notifications and track sync state.",
    )
    def post(self, request):
        from apps.accounts.models import Device

        ser = self._DeviceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        # One device record per user+platform — update push token if it exists
        device, created = Device.objects.update_or_create(
            user=request.user,
            platform=ser.validated_data["platform"],
            defaults={"push_token": ser.validated_data.get("push_token") or None},
        )

        return Response(
            {
                "id": str(device.id),
                "platform": device.platform,
                "push_token": device.push_token or "",
                "created_at": device.created_at,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(
        responses={200: _DeviceResponseSerializer(many=True)},
        summary="List user's devices",
    )
    def get(self, request):
        from apps.accounts.models import Device

        devices = Device.objects.filter(user=request.user).order_by("-created_at")
        return Response(
            [
                {
                    "id": str(d.id),
                    "platform": d.platform,
                    "push_token": d.push_token or "",
                    "last_seen": d.last_seen,
                    "created_at": d.created_at,
                }
                for d in devices
            ]
        )


class DeviceDetailView(APIView):
    """Remove a registered device (remote logout)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={204: None}, summary="Remove a device")
    def delete(self, request, device_id):
        from apps.accounts.models import Device

        try:
            device = Device.objects.get(id=device_id, user=request.user)
        except Device.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        device.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeExportView(APIView):
    """GET /me/export — export the user's own data as JSON (GDPR-style)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: {"type": "object"}},
        summary="Export user data",
        description=(
            "Returns a JSON dump of all data the consumer backend holds for the "
            "current user: profile, diet tags, pantry, saved recipes, cook log, "
            "meal plans, community submissions, and consent records. "
            "Does NOT include engine-side food data."
        ),
    )
    def get(self, request):
        user = request.user
        data = _build_user_export(user)
        return Response(data)


class MeDeleteView(APIView):
    """DELETE /me — soft-delete the account.

    The account is immediately deactivated. A Celery task purges all personal
    data after the configured grace period (default: 35 days).
    An audit event is logged.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={204: None},
        summary="Delete account",
        description=(
            "Soft-deletes the user's account. The account is deactivated immediately "
            "and all personal data is purged after a 35-day grace period. "
            "This action cannot be undone after the grace period."
        ),
    )
    def delete(self, request):
        from apps.accounts.tasks import purge_user_data_after_grace_period
        from apps.core.models import AuditEvent, log_audit_event

        user = request.user

        log_audit_event(
            action="account_deletion_requested",
            actor_id=str(user.id),
            actor_type=AuditEvent.ActorType.USER,
            object_type="user",
            object_id=str(user.id),
            ip_address=request.META.get("REMOTE_ADDR", ""),
        )

        user.soft_delete()

        # Schedule data purge after grace period (35 days)
        # In test environments (CELERY_TASK_ALWAYS_EAGER), this runs immediately but is harmless.
        from django.conf import settings as django_settings

        if getattr(django_settings, "CELERY_TASK_ALWAYS_EAGER", False):
            purge_user_data_after_grace_period.delay(str(user.id))
        else:
            purge_user_data_after_grace_period.apply_async(
                args=[str(user.id)],
                countdown=35 * 24 * 60 * 60,  # 35 days in seconds
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_user_export(user) -> dict:
    """Assemble all user data into a single exportable dict."""
    from apps.accounts.models import Consent, Device

    # Pantry
    try:
        from apps.pantry.models import PantryItem

        pantry = list(
            PantryItem.objects.filter(user=user).values(
                "ingredient_id", "ingredient_slug", "display_name", "added_at", "expires_on"
            )
        )
    except Exception:
        pantry = []

    # Saved recipes
    try:
        from apps.library.models import SavedRecipe

        saved = list(
            SavedRecipe.objects.filter(user=user).values(
                "dish_id", "dish_slug", "dataset_version", "note", "saved_at"
            )
        )
    except Exception:
        saved = []

    # Cook log
    try:
        from apps.library.models import CookLog

        cook_log = list(CookLog.objects.filter(user=user).values("dish_id", "cooked_at", "rating"))
    except Exception:
        cook_log = []

    # Meal plans
    try:
        from apps.planner.models import MealPlan, MealPlanEntry

        plans = []
        for plan in MealPlan.objects.filter(user=user):
            entries = list(
                MealPlanEntry.objects.filter(plan=plan).values(
                    "day", "meal_type", "dish_id", "dish_slug", "servings", "note"
                )
            )
            plans.append({"week_start": plan.week_start.isoformat(), "entries": entries})
    except Exception:
        plans = []

    # Submissions
    try:
        from apps.community.models import Submission

        submissions = list(
            Submission.objects.filter(user=user).values("id", "payload", "status", "created_at")
        )
    except Exception:
        submissions = []

    # Consents
    consents = list(
        Consent.objects.filter(user=user).values("type", "version", "granted_at", "revoked_at")
    )

    # Devices (no push tokens — those are operational, not personal data)
    devices = list(Device.objects.filter(user=user).values("platform", "last_seen", "created_at"))

    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "phone": user.phone,
            "language": user.language,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "pantry": pantry,
        "saved_recipes": saved,
        "cook_log": cook_log,
        "meal_plans": plans,
        "submissions": submissions,
        "consents": consents,
        "devices": devices,
    }
