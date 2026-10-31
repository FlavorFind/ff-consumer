"""Admin for notifications app."""

from django.contrib import admin

from apps.notifications.models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["user", "channel", "type", "title", "read_at", "created_at"]
    list_filter = ["channel", "type"]
    raw_id_fields = ["user"]
    readonly_fields = ["created_at", "sent_at", "read_at"]
    search_fields = ["user__email", "type", "title"]


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ["user", "push_enabled", "email_enabled", "updated_at"]
    raw_id_fields = ["user"]
    readonly_fields = ["updated_at"]
