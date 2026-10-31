"""Notifications views — in-app notifications list, preferences."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "channel",
            "type",
            "title",
            "body",
            "data",
            "read_at",
            "sent_at",
            "created_at",
        ]
        read_only_fields = fields


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            "push_enabled",
            "email_enabled",
            "quiet_hours_start",
            "quiet_hours_end",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


class NotificationListView(APIView):
    """GET /v1/notifications/ — list in-app notifications for the current user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: NotificationSerializer(many=True)},
        summary="List notifications",
        description="Returns the most recent 50 in-app notifications for the authenticated user.",
    )
    def get(self, request):
        notifications = (
            Notification.objects.filter(
                user=request.user,
                channel=Notification.Channel.IN_APP,
            )
            .order_by("-created_at")[:50]
        )
        return Response(NotificationSerializer(notifications, many=True).data)


class NotificationMarkReadView(APIView):
    """POST /v1/notifications/<id>/read/ — mark a notification as read."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={200: NotificationSerializer},
        summary="Mark notification as read",
    )
    def post(self, request, notification_id):
        from django.utils import timezone

        try:
            notification = Notification.objects.get(
                id=notification_id, user=request.user
            )
        except Notification.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not notification.read_at:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])

        return Response(NotificationSerializer(notification).data)


class NotificationPreferenceView(APIView):
    """GET/PATCH /v1/notifications/preferences/ — notification preferences."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: NotificationPreferenceSerializer},
        summary="Get notification preferences",
    )
    def get(self, request):
        pref, _ = NotificationPreference.objects.get_or_create(user=request.user)
        return Response(NotificationPreferenceSerializer(pref).data)

    @extend_schema(
        request=NotificationPreferenceSerializer,
        responses={200: NotificationPreferenceSerializer},
        summary="Update notification preferences",
    )
    def patch(self, request):
        pref, _ = NotificationPreference.objects.get_or_create(user=request.user)
        ser = NotificationPreferenceSerializer(pref, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)
