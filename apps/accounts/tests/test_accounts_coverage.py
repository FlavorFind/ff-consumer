"""Extended accounts tests — services, OTP flow, export, delete, serializers.

Targets 95%+ coverage for apps/accounts.
"""

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


# ---------------------------------------------------------------------------
# OTP service tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestOTPService:
    def test_request_otp_creates_record(self):
        from apps.accounts.models import OTPRequest
        from apps.accounts.services import request_otp

        request_otp("+254712000001")
        assert OTPRequest.objects.filter(phone="+254712000001").exists()

    def test_request_otp_cooldown_raises(self):
        from apps.accounts.services import request_otp

        request_otp("+254712000002")
        with pytest.raises(ValueError, match="wait"):
            request_otp("+254712000002")

    def test_verify_otp_no_pending_raises(self):
        from apps.accounts.services import verify_otp

        with pytest.raises(ValueError, match="No pending"):
            verify_otp("+254799000001", "123456")

    def test_verify_otp_expired_raises(self):
        from datetime import timedelta

        from apps.accounts.models import OTPRequest
        from apps.accounts.services import _hash_code, verify_otp

        OTPRequest.objects.create(
            phone="+254799000002",
            code_hash=_hash_code("111111"),
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        with pytest.raises(ValueError, match="expired"):
            verify_otp("+254799000002", "111111")

    def test_verify_otp_locked_raises(self):
        from apps.accounts.models import OTPRequest
        from apps.accounts.services import _hash_code, verify_otp

        OTPRequest.objects.create(
            phone="+254799000003",
            code_hash=_hash_code("222222"),
            expires_at=timezone.now() + timezone.timedelta(minutes=5),
            attempts=5,
        )
        with pytest.raises(ValueError, match="Too many"):
            verify_otp("+254799000003", "222222")

    def test_verify_otp_wrong_code_increments_attempts(self):
        from apps.accounts.models import OTPRequest
        from apps.accounts.services import _hash_code, verify_otp

        otp = OTPRequest.objects.create(
            phone="+254799000004",
            code_hash=_hash_code("333333"),
            expires_at=timezone.now() + timezone.timedelta(minutes=5),
        )
        with pytest.raises(ValueError, match="Incorrect"):
            verify_otp("+254799000004", "000000")
        otp.refresh_from_db()
        assert otp.attempts == 1

    def test_verify_otp_creates_new_user(self):
        from apps.accounts.models import OTPRequest
        from apps.accounts.services import _hash_code, verify_otp

        OTPRequest.objects.create(
            phone="+254799000005",
            code_hash=_hash_code("444444"),
            expires_at=timezone.now() + timezone.timedelta(minutes=5),
        )
        user = verify_otp("+254799000005", "444444")
        assert user.phone == "+254799000005"
        assert User.objects.filter(phone="+254799000005").exists()

    def test_verify_otp_returns_existing_user(self):
        from apps.accounts.models import OTPRequest
        from apps.accounts.services import _hash_code, verify_otp

        existing = User.objects.create_user(phone="+254799000006")
        OTPRequest.objects.create(
            phone="+254799000006",
            code_hash=_hash_code("555555"),
            expires_at=timezone.now() + timezone.timedelta(minutes=5),
        )
        user = verify_otp("+254799000006", "555555")
        assert user.id == existing.id

    def test_verify_otp_marks_used(self):
        from apps.accounts.models import OTPRequest
        from apps.accounts.services import _hash_code, verify_otp

        otp = OTPRequest.objects.create(
            phone="+254799000007",
            code_hash=_hash_code("666666"),
            expires_at=timezone.now() + timezone.timedelta(minutes=5),
        )
        verify_otp("+254799000007", "666666")
        otp.refresh_from_db()
        assert otp.used_at is not None

    def test_otp_request_model_properties(self):
        from datetime import timedelta

        from apps.accounts.models import OTPRequest
        from apps.accounts.services import _hash_code

        otp_expired = OTPRequest(
            phone="+254799999",
            code_hash=_hash_code("x"),
            expires_at=timezone.now() - timedelta(minutes=1),
            attempts=0,
        )
        assert otp_expired.is_expired is True
        assert otp_expired.is_used is False

        otp_locked = OTPRequest(
            phone="+254799999",
            code_hash=_hash_code("x"),
            expires_at=timezone.now() + timedelta(minutes=5),
            attempts=5,
        )
        assert otp_locked.is_locked is True


# ---------------------------------------------------------------------------
# User model tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUserModel:
    def test_soft_delete(self, user):
        user.soft_delete()
        user.refresh_from_db()
        assert user.status == User.Status.DELETED
        assert user.is_active is False
        assert user.deleted_at is not None
        assert user.is_deleted is True

    def test_create_user_no_email_no_phone_raises(self):
        with pytest.raises(ValueError, match="email or a phone"):
            User.objects.create_user()

    def test_create_superuser(self):
        su = User.objects.create_superuser(email="su@example.com", password="SuperPass123!")
        assert su.is_staff is True
        assert su.is_superuser is True

    def test_user_str_email(self, user):
        assert str(user) == user.email

    def test_user_str_phone_no_email(self):
        u = User.objects.create_user(phone="+254711000001")
        assert str(u) == "+254711000001"


# ---------------------------------------------------------------------------
# Serializer tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRegisterSerializer:
    def test_valid_data(self):
        from apps.accounts.serializers import RegisterSerializer

        ser = RegisterSerializer(
            data={"email": "ser@example.com", "password": "StrongPass1!", "language": "sw"}
        )
        assert ser.is_valid(), ser.errors
        user = ser.save()
        assert user.email == "ser@example.com"
        assert user.language == "sw"

    def test_invalid_email(self):
        from apps.accounts.serializers import RegisterSerializer

        ser = RegisterSerializer(data={"email": "not-an-email", "password": "StrongPass1!"})
        assert not ser.is_valid()
        assert "email" in ser.errors

    def test_weak_password_rejected(self):
        from apps.accounts.serializers import RegisterSerializer

        ser = RegisterSerializer(data={"email": "ok@example.com", "password": "abc"})
        assert not ser.is_valid()

    def test_duplicate_email_rejected(self, user):
        from apps.accounts.serializers import RegisterSerializer

        ser = RegisterSerializer(data={"email": user.email, "password": "StrongPass1!"})
        assert not ser.is_valid()


# ---------------------------------------------------------------------------
# Me export / delete endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMeExport:
    def test_export_returns_user_data(self, auth_client, user):
        response = auth_client.get("/v1/me/export")
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["email"] == user.email
        assert "pantry" in data
        assert "saved_recipes" in data
        assert "cook_log" in data
        assert "meal_plans" in data
        assert "submissions" in data
        assert "consents" in data
        assert "devices" in data

    def test_export_requires_auth(self, api_client):
        response = api_client.get("/v1/me/export")
        assert response.status_code == 401


@pytest.mark.django_db
class TestMeDelete:
    def test_delete_soft_deletes_user(self, auth_client, user):
        response = auth_client.delete("/v1/me/delete")
        assert response.status_code == 204
        user.refresh_from_db()
        assert user.status == User.Status.DELETED
        assert user.is_active is False

    def test_delete_requires_auth(self, api_client):
        response = api_client.delete("/v1/me/delete")
        assert response.status_code == 401

    def test_delete_logs_audit_event(self, auth_client, user):
        from unittest.mock import patch

        with patch("apps.accounts.tasks.purge_user_data_after_grace_period.delay") as mock_task:
            auth_client.delete("/v1/me/delete")
            assert mock_task.called
            args = mock_task.call_args[0]
            assert args[0] == str(user.id)

        from apps.core.models import AuditEvent

        assert AuditEvent.objects.filter(
            actor_id=str(user.id), action="account_deletion_requested"
        ).exists()


# ---------------------------------------------------------------------------
# Purge task (direct call)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPurgeTask:
    def test_purge_no_op_for_active_user(self, user):
        """Purge task skips users who are not in DELETED status."""
        from apps.accounts.tasks import purge_user_data_after_grace_period

        # Call task directly — user is active, should be no-op
        purge_user_data_after_grace_period(str(user.id))
        user.refresh_from_db()
        assert user.status == User.Status.ACTIVE  # unchanged

    def test_purge_no_op_for_missing_user(self):
        """Purge task handles missing user gracefully."""
        import uuid

        from apps.accounts.tasks import purge_user_data_after_grace_period

        # Should not raise
        purge_user_data_after_grace_period(str(uuid.uuid4()))

    def test_purge_anonymises_deleted_user(self, user):
        """Purge task anonymises user data after soft delete."""
        from apps.accounts.tasks import purge_user_data_after_grace_period

        user.soft_delete()
        original_email = user.email

        purge_user_data_after_grace_period(str(user.id))

        user.refresh_from_db()
        assert user.email != original_email
        assert "deleted" in user.email
        assert user.phone is None

    def test_purge_removes_pantry_items(self, user):
        """Purge removes pantry items for the deleted user."""
        from apps.accounts.tasks import purge_user_data_after_grace_period
        from apps.pantry.models import PantryItem

        PantryItem.objects.create(
            user=user,
            ingredient_id="00000000-0000-0000-0000-000000000001",
            ingredient_slug="tomato",
            display_name="Tomato",
        )
        user.soft_delete()
        purge_user_data_after_grace_period(str(user.id))
        assert PantryItem.objects.filter(user=user).count() == 0


# ---------------------------------------------------------------------------
# OTP endpoints
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestOTPEndpoints:
    def test_otp_request_valid_phone(self, api_client):
        response = api_client.post(
            "/v1/auth/otp/request",
            {"phone": "+254712000099"},
            format="json",
        )
        assert response.status_code == 200
        assert "detail" in response.json()

    def test_otp_verify_invalid_code(self, api_client):
        from apps.accounts.models import OTPRequest
        from apps.accounts.services import _hash_code

        OTPRequest.objects.create(
            phone="+254711000099",
            code_hash=_hash_code("123456"),
            expires_at=timezone.now() + timezone.timedelta(minutes=5),
        )
        response = api_client.post(
            "/v1/auth/otp/verify",
            {"phone": "+254711000099", "code": "000000"},
            format="json",
        )
        assert response.status_code == 400
        assert "otp_invalid" in response.json().get("error", {}).get("code", "")

    def test_otp_verify_success(self, api_client):
        from apps.accounts.models import OTPRequest
        from apps.accounts.services import _hash_code

        OTPRequest.objects.create(
            phone="+254711000098",
            code_hash=_hash_code("123456"),
            expires_at=timezone.now() + timezone.timedelta(minutes=5),
        )
        response = api_client.post(
            "/v1/auth/otp/verify",
            {"phone": "+254711000098", "code": "123456"},
            format="json",
        )
        assert response.status_code == 200
        assert "access" in response.json()

    def test_logout_missing_refresh_token(self, auth_client):
        response = auth_client.post("/v1/auth/logout", {}, format="json")
        assert response.status_code == 400

    def test_logout_invalid_refresh_token(self, auth_client):
        # Already-invalid token should still return 204 (silently ignored)
        response = auth_client.post("/v1/auth/logout", {"refresh": "invalidtoken"}, format="json")
        assert response.status_code == 204
