"""URL patterns for the accounts app."""

from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts import views

urlpatterns = [
    path("auth/register", views.RegisterView.as_view(), name="auth-register"),
    path("auth/login", TokenObtainPairView.as_view(), name="auth-login"),
    path("auth/otp/request", views.OTPRequestView.as_view(), name="auth-otp-request"),
    path("auth/otp/verify", views.OTPVerifyView.as_view(), name="auth-otp-verify"),
    path("auth/refresh", TokenRefreshView.as_view(), name="auth-refresh"),
    path("auth/logout", views.LogoutView.as_view(), name="auth-logout"),
    path("me", views.MeView.as_view(), name="me"),
    path("me/export", views.MeExportView.as_view(), name="me-export"),
    path("me/delete", views.MeDeleteView.as_view(), name="me-delete"),
    path("me/devices", views.DeviceView.as_view(), name="me-devices"),
    path("me/devices/<uuid:device_id>", views.DeviceDetailView.as_view(), name="me-device-detail"),
]
