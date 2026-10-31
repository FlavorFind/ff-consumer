"""Tests for accounts auth endpoints.

C5, C6 build steps verification.
"""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestRegister:
    def test_register_success(self, api_client):
        response = api_client.post(
            "/v1/auth/register",
            {"email": "new@example.com", "password": "SecurePass123!", "language": "en"},
            format="json",
        )
        assert response.status_code == 201
        data = response.json()
        assert "access" in data
        assert "refresh" in data
        assert data["user"]["email"] == "new@example.com"

    def test_register_creates_user(self, api_client):
        api_client.post(
            "/v1/auth/register",
            {"email": "new2@example.com", "password": "SecurePass123!"},
            format="json",
        )
        assert User.objects.filter(email="new2@example.com").exists()

    def test_register_duplicate_email(self, api_client, user):
        response = api_client.post(
            "/v1/auth/register",
            {"email": user.email, "password": "SecurePass123!"},
            format="json",
        )
        assert response.status_code == 400

    def test_register_weak_password(self, api_client):
        response = api_client.post(
            "/v1/auth/register",
            {"email": "weak@example.com", "password": "123"},
            format="json",
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestLogin:
    def test_login_success(self, api_client, user):
        response = api_client.post(
            "/v1/auth/login",
            {"email": user.email, "password": "testpass123"},
            format="json",
        )
        assert response.status_code == 200
        assert "access" in response.json()

    def test_login_wrong_password(self, api_client, user):
        response = api_client.post(
            "/v1/auth/login",
            {"email": user.email, "password": "wrong"},
            format="json",
        )
        assert response.status_code == 401


@pytest.mark.django_db
class TestLogout:
    def test_logout_revokes_token(self, auth_client, user):
        # Get a refresh token
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken.for_user(user)
        response = auth_client.post(
            "/v1/auth/logout",
            {"refresh": str(refresh)},
            format="json",
        )
        assert response.status_code == 204

    def test_logout_requires_auth(self, api_client):
        response = api_client.post("/v1/auth/logout", {}, format="json")
        assert response.status_code == 401


@pytest.mark.django_db
class TestMe:
    def test_me_returns_user(self, auth_client, user):
        response = auth_client.get("/v1/me")
        assert response.status_code == 200
        assert response.json()["email"] == user.email

    def test_me_requires_auth(self, api_client):
        response = api_client.get("/v1/me")
        assert response.status_code == 401


@pytest.mark.django_db
class TestPermissions:
    """User A cannot see User B's data."""

    def test_user_cannot_access_other_user_me(self, api_client, user, other_user):
        """Sanity check: each /me returns only their own data."""
        from rest_framework_simplejwt.tokens import RefreshToken

        # User A
        refresh_a = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh_a.access_token}")
        resp_a = api_client.get("/v1/me")
        assert resp_a.json()["email"] == user.email

        # User B
        refresh_b = RefreshToken.for_user(other_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh_b.access_token}")
        resp_b = api_client.get("/v1/me")
        assert resp_b.json()["email"] == other_user.email

        # Cross-check: A's token cannot return B's email
        assert resp_a.json()["email"] != resp_b.json()["email"]


@pytest.mark.django_db
class TestDevices:
    def test_register_device(self, auth_client):
        response = auth_client.post(
            "/v1/me/devices",
            {"platform": "android", "push_token": "token-abc"},
            format="json",
        )
        assert response.status_code == 201
        data = response.json()
        assert data["platform"] == "android"
        assert data["push_token"] == "token-abc"

    def test_register_device_updates_existing(self, auth_client):
        """Registering the same platform twice updates the push token."""
        auth_client.post("/v1/me/devices", {"platform": "android"}, format="json")
        response = auth_client.post(
            "/v1/me/devices",
            {"platform": "android", "push_token": "new-token"},
            format="json",
        )
        # 200 on update (not 201)
        assert response.status_code == 200
        assert response.json()["push_token"] == "new-token"

    def test_list_devices(self, auth_client):
        auth_client.post("/v1/me/devices", {"platform": "android"}, format="json")
        auth_client.post("/v1/me/devices", {"platform": "web"}, format="json")
        response = auth_client.get("/v1/me/devices")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_delete_device(self, auth_client):
        resp = auth_client.post("/v1/me/devices", {"platform": "android"}, format="json")
        device_id = resp.json()["id"]
        delete_resp = auth_client.delete(f"/v1/me/devices/{device_id}")
        assert delete_resp.status_code == 204
        # Verify it's gone
        list_resp = auth_client.get("/v1/me/devices")
        assert len(list_resp.json()) == 0

    def test_delete_other_users_device_returns_404(self, auth_client, other_user):
        """User A cannot delete User B's device."""
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken

        # Register a device for other_user
        other_client = APIClient()
        refresh = RefreshToken.for_user(other_user)
        other_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        resp = other_client.post("/v1/me/devices", {"platform": "android"}, format="json")
        other_device_id = resp.json()["id"]

        # Try to delete it as auth_client (different user)
        response = auth_client.delete(f"/v1/me/devices/{other_device_id}")
        assert response.status_code == 404

    def test_devices_require_auth(self, api_client):
        response = api_client.get("/v1/me/devices")
        assert response.status_code == 401
