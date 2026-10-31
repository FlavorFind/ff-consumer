"""Extended accounts tests — email verification flow, export, delete, serializers.

Targets 95%+ coverage for apps/accounts.
"""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


# ---------------------------------------------------------------------------
# Email verification service tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEmailVerificationService:
    def test_send_verification_creates_token(self, user):
        from apps.accounts.models import EmailVerification
        from apps.accounts.services import send_verification_email

        send_verification_email(user)
        assert EmailVerification.objects.filter(user=user, used_at__isnull=True).exists()

    def test_send_verification_invalidates_previous_tokens(self, user):
        from apps.accounts.models import EmailVerification
        from apps.accounts.services import send_verification_email

        send_verification_email(user)
        send_verification_email(user)
        # Only the latest (unused) token should remain
        assert EmailVerification.objects.filter(user=user, used_at__isnull=True).count() == 1

    def test_verify_token_marks_email_verified(self, user):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import EmailVerification
        from apps.accounts.services import _generate_token, _hash_token, verify_email_token

        token = _generate_token()
        EmailVerification.objects.create(
            user=user,
            token=_hash_token(token),
            expires_at=timezone.now() + timedelta(hours=24),
        )

        result = verify_email_token(token)
        assert result.email_verified is True

    def test_verify_invalid_token_raises(self):
        from apps.accounts.services import verify_email_token

        with pytest.raises(ValueError, match="Invalid"):
            verify_email_token("notavalidtoken")

    def test_verify_expired_token_raises(self, user):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import EmailVerification
        from apps.accounts.services import _generate_token, _hash_token, verify_email_token

        token = _generate_token()
        EmailVerification.objects.create(
            user=user,
            token=_hash_token(token),
            expires_at=timezone.now() - timedelta(hours=1),  # already expired
        )

        with pytest.raises(ValueError, match="expired"):
            verify_email_token(token)

    def test_verify_already_used_token_raises(self, user):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import EmailVerification
        from apps.accounts.services import _generate_token, _hash_token, verify_email_token

        token = _generate_token()
        EmailVerification.objects.create(
            user=user,
            token=_hash_token(token),
            expires_at=timezone.now() + timedelta(hours=24),
            used_at=timezone.now(),  # already used
        )

        with pytest.raises(ValueError, match="Invalid"):
            verify_email_token(token)


# ---------------------------------------------------------------------------
# Email verification views
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEmailVerifyView:
    def test_valid_token_verifies_email(self, api_client, user):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import EmailVerification
        from apps.accounts.services import _generate_token, _hash_token

        token = _generate_token()
        EmailVerification.objects.create(
            user=user,
            token=_hash_token(token),
            expires_at=timezone.now() + timedelta(hours=24),
        )

        response = api_client.post("/v1/auth/verify-email/", {"token": token}, format="json")
        assert response.status_code == 200
        assert response.json()["email_verified"] is True

    def test_invalid_token_returns_400(self, api_client):
        response = api_client.post("/v1/auth/verify-email/", {"token": "badtoken"}, format="json")
        assert response.status_code == 400

    def test_no_token_returns_400(self, api_client):
        response = api_client.post("/v1/auth/verify-email/", {}, format="json")
        assert response.status_code == 400


@pytest.mark.django_db
class TestResendVerificationView:
    def test_resend_for_unverified_user(self, api_client, user):
        # RESEND_API_KEY is empty in test — email is skipped silently
        response = api_client.post(
            "/v1/auth/resend-verification/", {"email": user.email}, format="json"
        )
        assert response.status_code == 200
        assert "verification link" in response.json()["detail"].lower()

    def test_resend_for_nonexistent_email(self, api_client):
        response = api_client.post(
            "/v1/auth/resend-verification/",
            {"email": "nobody@example.com"},
            format="json",
        )
        # Does not reveal whether email exists
        assert response.status_code == 200

    def test_resend_for_already_verified_user(self, api_client, user):
        user.email_verified = True
        user.save()
        response = api_client.post(
            "/v1/auth/resend-verification/", {"email": user.email}, format="json"
        )
        assert response.status_code == 200
        assert "already verified" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRegistration:
    def test_register_creates_user(self, api_client):
        response = api_client.post(
            "/v1/auth/register/",
            {
                "email": "newuser@example.com",
                "username": "newuser",
                "password": "StrongPass123!",
            },
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["user"]["email"] == "newuser@example.com"
        assert response.json()["user"]["email_verified"] is False
        assert "access" in response.json()
        assert "refresh" in response.json()

    def test_register_duplicate_email_returns_400(self, api_client, user):
        response = api_client.post(
            "/v1/auth/register/",
            {"email": user.email, "username": "other", "password": "StrongPass123!"},
            format="json",
        )
        assert response.status_code == 400

    def test_register_duplicate_username_returns_400(self, api_client, user):
        response = api_client.post(
            "/v1/auth/register/",
            {
                "email": "unique@example.com",
                "username": user.username,
                "password": "StrongPass123!",
            },
            format="json",
        )
        assert response.status_code == 400

    def test_register_invalid_username_chars(self, api_client):
        response = api_client.post(
            "/v1/auth/register/",
            {
                "email": "valid@example.com",
                "username": "bad username!",
                "password": "StrongPass123!",
            },
            format="json",
        )
        assert response.status_code == 400

    def test_register_weak_password_returns_400(self, api_client):
        response = api_client.post(
            "/v1/auth/register/",
            {"email": "x@example.com", "username": "xuser", "password": "123"},
            format="json",
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUserModel:
    def test_create_user_requires_email(self):
        with pytest.raises(ValueError, match="email"):
            User.objects.create_user(email="", username="x", password="pass")

    def test_soft_delete(self, user):
        user.soft_delete()
        assert user.is_deleted is True
        assert user.is_active is False
        assert user.status == User.Status.DELETED

    def test_str_returns_email(self, user):
        assert str(user) == user.email


# ---------------------------------------------------------------------------
# Export and delete
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMeExport:
    def test_export_returns_user_data(self, auth_client, user):
        response = auth_client.get("/v1/me/export/")
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["email"] == user.email
        assert data["user"]["username"] == user.username
        assert "pantry" in data
        assert "saved_recipes" in data

    def test_export_requires_auth(self, api_client):
        assert api_client.get("/v1/me/export/").status_code == 401


@pytest.mark.django_db
class TestMeDelete:
    def test_delete_account_deactivates_user(self, auth_client, user):
        response = auth_client.delete("/v1/me/delete/")
        assert response.status_code == 204
        user.refresh_from_db()
        assert user.status == User.Status.DELETED
        assert user.is_active is False

    def test_delete_requires_auth(self, api_client):
        assert api_client.delete("/v1/me/delete/").status_code == 401


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetTokens:
    def test_get_tokens_returns_access_and_refresh(self, user):
        from apps.accounts.services import get_tokens_for_user

        tokens = get_tokens_for_user(user)
        assert "access" in tokens
        assert "refresh" in tokens
