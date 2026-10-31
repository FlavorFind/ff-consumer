"""URL patterns for the sync app."""

from django.urls import path

from apps.sync import views

urlpatterns = [
    path("sync/push/", views.SyncPushView.as_view(), name="sync-push"),
    path("sync/pull/", views.SyncPullView.as_view(), name="sync-pull"),
]
