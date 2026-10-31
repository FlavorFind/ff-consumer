"""Notifications models — push, email, in-app, preferences."""

import uuid

from django.conf import settings
from django.db import models


class Notification(models.Model):
    """An in-app or push notification sent to a user."""

    class Channel(models.TextChoices):
        PUSH = "push", "Push"
        EMAIL = "email", "Email"
        IN_APP = "in_app", "In-App"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    channel = models.CharField(max_length=10, choices=Channel.choices)
    type = models.CharField(max_length=100, db_index=True)  # e.g. "meal_reminder"
    title = models.CharField(max_length=300)
    body = models.TextField()
    data = models.JSONField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} — {self.type} ({self.channel})"


class NotificationPreference(models.Model):
    """Per-user notification preferences."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    push_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} preferences"
