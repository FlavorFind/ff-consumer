"""URL patterns for the notifications app."""

from django.urls import path

from apps.notifications import views

urlpatterns = [
    path("notifications/", views.NotificationListView.as_view(), name="notifications"),
    path(
        "notifications/preferences/",
        views.NotificationPreferenceView.as_view(),
        name="notification-preferences",
    ),
    path(
        "notifications/<uuid:notification_id>/read/",
        views.NotificationMarkReadView.as_view(),
        name="notification-mark-read",
    ),
]
