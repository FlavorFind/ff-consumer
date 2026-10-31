"""URL patterns for the profiles app."""

from django.urls import path

from apps.profiles import views

urlpatterns = [
    path("me/profile", views.ProfileView.as_view(), name="profile"),
    path("me/diet", views.ProfileDietView.as_view(), name="profile-diet"),
]
