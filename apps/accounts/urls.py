"""URL patterns for the accounts app."""

from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts import views
from apps.accounts.serializers import CustomTokenObtainPairSerializer


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


urlpatterns = [
    # Registration and email verification
    path("auth/register/", views.RegisterView.as_view(), name="auth-register"),
    path("auth/verify-email/", views.EmailVerifyView.as_view(), name="auth-verify-email"),
    path(
        "auth/resend-verification/",
        views.ResendVerificationView.as_view(),
        name="auth-resend-verification",
    ),
    # Login / token management
    path("auth/login/", CustomTokenObtainPairView.as_view(), name="auth-login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    # Current user
    path("me/", views.MeView.as_view(), name="me"),
    path("me/export/", views.MeExportView.as_view(), name="me-export"),
    path("me/delete/", views.MeDeleteView.as_view(), name="me-delete"),
    path("me/devices/", views.DeviceView.as_view(), name="me-devices"),
    path(
        "me/devices/<uuid:device_id>/",
        views.DeviceDetailView.as_view(),
        name="me-device-detail",
    ),
]
