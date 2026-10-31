"""Auth views for ff-consumer."""

import logging

from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.serializers import (
    EmailVerifySerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    TokenResponseSerializer,
    UserSerializer,
)
from apps.accounts.services import (
    get_tokens_for_user,
    send_verification_email,
    verify_email_token,
)

logger = logging.getLogger(__name__)

User = get_user_model()


class RegisterView(APIView):
    """Register a new user with email, username, and password.

    Sends a verification email via Resend after successful registration.
    The user can log in immediately but email_verified will be False until
    they click the verification link.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=RegisterSerializer,
        responses={201: TokenResponseSerializer},
        summary="Register",
        description=(
            "Create a new account with email, username, and password. "
            "A verification email is sent automatically. "
            "Login works immediately — email verification is not required to use the app."
        ),
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Send verification email — failure here does not block registration
        try:
            send_verification_email(user)
        except Exception as exc:
            logger.error("Failed to send verification email to %s: %s", user.email, exc)

        tokens = get_tokens_for_user(user)
        return Response(
            {**tokens, "user": UserSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )


class EmailVerifyView(APIView):
    """POST /v1/auth/verify-email/ — verify email with token from the email link."""

    permission_classes = [AllowAny]

    @extend_schema(
        request=EmailVerifySerializer,
        responses={200: UserSerializer},
        summary="Verify email address",
        description="Submit the token from the verification email to confirm the email address.",
    )
    def post(self, request):
        ser = EmailVerifySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            user = verify_email_token(ser.validated_data["token"])
        except ValueError as exc:
            return Response(
                {"error": {"code": "invalid_token", "message": str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(UserSerializer(user).data)


class ResendVerificationView(APIView):
    """POST /v1/auth/resend-verification/ — send a fresh verification email."""

    permission_classes = [AllowAny]

    @extend_schema(
        request=ResendVerificationSerializer,
        responses={200: {"type": "object", "properties": {"detail": {"type": "string"}}}},
        summary="Resend verification email",
    )
    def post(self, request):
        ser = ResendVerificationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            user = User.objects.get(email=ser.validated_data["email"])
        except User.DoesNotExist:
            # Don't reveal whether the email exists
            return Response(
                {"detail": "If that email is registered, a verification link has been sent."}
            )

        if user.email_verified:
            return Response({"detail": "Email is already verified."})

        try:
            send_verification_email(user)
        except Exception as exc:
            logger.error("Failed to resend verification email to %s: %s", user.email, exc)

        return Response(
            {"detail": "If that email is registered, a verification link has been sent."}
        )


class _LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class LogoutView(APIView):
    """Revoke the refresh token — effectively logs the user out."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=_LogoutRequestSerializer,
        responses={204: None},
        summary="Logout",
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
            pass
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """Current user's details."""

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
    )
    def post(self, request):
        from apps.accounts.models import Device

        ser = self._DeviceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
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
    """GET /v1/me/export/ — export the user's own data as JSON."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: {"type": "object"}},
        summary="Export user data",
        description=(
            "Returns a JSON dump of all data the backend holds for the current user: "
            "profile, diet tags, pantry, saved recipes, cook log, meal plans, "
            "submissions, and consent records."
        ),
    )
    def get(self, request):
        return Response(_build_user_export(request.user))


class MeDeleteView(APIView):
    """DELETE /v1/me/delete/ — soft-delete the account."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={204: None},
        summary="Delete account",
        description=(
            "Soft-deletes the account immediately. All personal data is purged "
            "after a 35-day grace period."
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

        from django.conf import settings as django_settings

        if getattr(django_settings, "CELERY_TASK_ALWAYS_EAGER", False):
            purge_user_data_after_grace_period.delay(str(user.id))
        else:
            purge_user_data_after_grace_period.apply_async(
                args=[str(user.id)],
                countdown=35 * 24 * 60 * 60,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_user_export(user) -> dict:
    from apps.accounts.models import Consent, Device

    try:
        from apps.pantry.models import PantryItem

        pantry = list(
            PantryItem.objects.filter(user=user).values(
                "ingredient_id", "ingredient_slug", "display_name", "added_at", "expires_on"
            )
        )
    except Exception:
        pantry = []

    try:
        from apps.library.models import SavedRecipe

        saved = list(
            SavedRecipe.objects.filter(user=user).values(
                "dish_id", "dish_slug", "dataset_version", "note", "saved_at"
            )
        )
    except Exception:
        saved = []

    try:
        from apps.library.models import CookLog

        cook_log = list(CookLog.objects.filter(user=user).values("dish_id", "cooked_at", "rating"))
    except Exception:
        cook_log = []

    try:
        from apps.planner.models import MealPlan, MealPlanEntry

        plans = []
        for plan in MealPlan.objects.filter(user=user):
            entries = list(
                MealPlanEntry.objects.filter(plan=plan).values(
                    "day", "meal_type", "dish_id", "dish_slug", "servings", "note"
                )
            )
            plans.append({"week_start": str(plan.week_start), "entries": entries})
    except Exception:
        plans = []

    try:
        from apps.community.models import Submission

        submissions = list(
            Submission.objects.filter(user=user).values("id", "payload", "status", "created_at")
        )
    except Exception:
        submissions = []

    consents = list(
        Consent.objects.filter(user=user).values("type", "version", "granted_at", "revoked_at")
    )
    devices = list(Device.objects.filter(user=user).values("platform", "last_seen", "created_at"))

    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "language": user.language,
            "email_verified": user.email_verified,
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
