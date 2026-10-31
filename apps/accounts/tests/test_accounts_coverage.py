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


# ---------------------------------------------------------------------------
# User model — create_superuser, no-password user, properties
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUserModelExtended:
    def test_create_superuser(self):
        u = User.objects.create_superuser(
            email="admin@example.com", username="admin", password="AdminPass123!"
        )
        assert u.is_staff is True
        assert u.is_superuser is True
        assert u.status == User.Status.ACTIVE
        assert u.email_verified is True

    def test_create_user_without_password_sets_unusable(self):
        u = User.objects.create_user(email="nopass@example.com", username="nopass", password="")
        assert not u.has_usable_password()

    def test_create_superuser_requires_staff(self):
        with pytest.raises(ValueError, match="is_staff"):
            User.objects.create_superuser(
                email="bad@example.com", username="bad", password="pass", is_staff=False
            )

    def test_create_superuser_requires_superuser(self):
        with pytest.raises(ValueError, match="is_superuser"):
            User.objects.create_superuser(
                email="bad2@example.com", username="bad2", password="pass", is_superuser=False
            )


# ---------------------------------------------------------------------------
# EmailVerification model properties
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEmailVerificationModel:
    def test_is_expired_true(self, user):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import EmailVerification

        v = EmailVerification.objects.create(
            user=user, token="abc", expires_at=timezone.now() - timedelta(hours=1)
        )
        assert v.is_expired is True

    def test_is_expired_false(self, user):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import EmailVerification

        v = EmailVerification.objects.create(
            user=user, token="abc", expires_at=timezone.now() + timedelta(hours=1)
        )
        assert v.is_expired is False

    def test_is_used_true(self, user):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import EmailVerification

        v = EmailVerification.objects.create(
            user=user,
            token="abc",
            expires_at=timezone.now() + timedelta(hours=1),
            used_at=timezone.now(),
        )
        assert v.is_used is True

    def test_is_used_false(self, user):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import EmailVerification

        v = EmailVerification.objects.create(
            user=user,
            token="abc",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        assert v.is_used is False


# ---------------------------------------------------------------------------
# Services — _send_via_resend with API key
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSendViaResend:
    def test_send_with_api_key_calls_resend_api(self):
        from unittest.mock import MagicMock, patch

        from apps.accounts.services import _send_via_resend

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"id": "resend-id-123"}

        with (
            patch("apps.accounts.services.settings.RESEND_API_KEY", "re_test_key"),
            patch("apps.accounts.services.settings.RESEND_FROM_EMAIL", "test@flavorfind.co.ke"),
            patch("requests.post") as mock_post,
        ):
            mock_post.return_value = mock_response
            _send_via_resend(
                to="user@example.com",
                subject="Test",
                html="<p>Hi</p>",
            )
            assert mock_post.call_count == 1
            call_args = mock_post.call_args
            assert call_args.kwargs["headers"]["Authorization"] == "Bearer re_test_key"
            assert call_args.kwargs["json"]["to"] == ["user@example.com"]

    def test_send_api_error_is_caught_and_logged(self):
        from unittest.mock import patch

        from apps.accounts.services import _send_via_resend

        with (
            patch("apps.accounts.services.settings.RESEND_API_KEY", "re_test_key"),
            patch("apps.accounts.services.settings.RESEND_FROM_EMAIL", "test@flavorfind.co.ke"),
            patch("requests.post") as mock_post,
        ):
            mock_post.side_effect = ConnectionError("Network down")
            # Should not raise — error is caught
            _send_via_resend(to="user@example.com", subject="Test", html="<p>Hi</p>")


# ---------------------------------------------------------------------------
# Views — registration email failure, logout, delete with eager Celery
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRegistrationEmailFailure:
    def test_register_succeeds_even_if_email_send_fails(self, api_client, mocker):
        """Registration returns 201 even when send_verification_email raises."""
        mocker.patch(
            "apps.accounts.views.send_verification_email",
            side_effect=RuntimeError("Email service down"),
        )
        response = api_client.post(
            "/v1/auth/register/",
            {
                "email": "emailfail@example.com",
                "username": "emailfail",
                "password": "StrongPass123!",
            },
            format="json",
        )
        assert response.status_code == 201


@pytest.mark.django_db
class TestResendVerificationEmailFailure:
    def test_resend_succeeds_even_if_email_send_fails(self, api_client, user, mocker):
        mocker.patch(
            "apps.accounts.views.send_verification_email",
            side_effect=RuntimeError("Email service down"),
        )
        response = api_client.post(
            "/v1/auth/resend-verification/", {"email": user.email}, format="json"
        )
        assert response.status_code == 200


@pytest.mark.django_db
class TestLogoutView:
    def test_logout_without_refresh_token_returns_400(self, auth_client):
        response = auth_client.post("/v1/auth/logout/", {}, format="json")
        assert response.status_code == 400

    def test_logout_with_invalid_refresh_returns_204(self, auth_client):
        """Invalid/expired refresh token still returns 204 (idempotent logout)."""
        response = auth_client.post(
            "/v1/auth/logout/", {"refresh": "invalid-token-string"}, format="json"
        )
        assert response.status_code == 204

    def test_logout_requires_auth(self, api_client):
        assert (
            api_client.post("/v1/auth/logout/", {"refresh": "x"}, format="json").status_code == 401
        )


@pytest.mark.django_db
class TestDeleteAccountEagerCelery:
    def test_delete_with_non_eager_celery_uses_apply_async(self, auth_client, user, mocker):
        """When CELERY_TASK_ALWAYS_EAGER is False, .apply_async() is used."""
        from django.test import override_settings

        mock_apply = mocker.patch(
            "apps.accounts.tasks.purge_user_data_after_grace_period.apply_async"
        )
        with override_settings(CELERY_TASK_ALWAYS_EAGER=False):
            response = auth_client.delete("/v1/me/delete/")
        assert response.status_code == 204
        mock_apply.assert_called_once()


@pytest.mark.django_db
class TestBuildUserExport:
    def test_export_includes_all_data_sections(self, auth_client, user):
        """Export returns all sections even when some are empty."""
        response = auth_client.get("/v1/me/export/")
        assert response.status_code == 200
        data = response.json()
        assert "user" in data
        assert "pantry" in data
        assert "saved_recipes" in data
        assert "cook_log" in data
        assert "meal_plans" in data
        assert "submissions" in data
        assert "consents" in data

    def test_export_with_pantry_items(self, auth_client, user):
        from apps.pantry.models import PantryItem

        PantryItem.objects.create(
            user=user,
            ingredient_id="11111111-1111-1111-1111-111111111111",
            ingredient_slug="tomato",
            display_name="Tomato",
        )
        response = auth_client.get("/v1/me/export/")
        assert response.status_code == 200
        assert len(response.json()["pantry"]) == 1
        assert response.json()["pantry"][0]["ingredient_slug"] == "tomato"

    def test_export_with_saved_recipes_and_cook_log(self, auth_client, user):
        from apps.library.models import CookLog, SavedRecipe

        SavedRecipe.objects.create(
            user=user,
            dish_id="22222222-2222-2222-2222-222222222222",
            dish_slug="ugali-sukuma",
            dataset_version="2026.10.0",
        )
        CookLog.objects.create(user=user, dish_id="22222222-2222-2222-2222-222222222222", rating=5)
        response = auth_client.get("/v1/me/export/")
        data = response.json()
        assert len(data["saved_recipes"]) == 1
        assert len(data["cook_log"]) == 1
        assert data["cook_log"][0]["rating"] == 5

    def test_export_with_meal_plans(self, auth_client, user):
        from apps.planner.models import MealPlan, MealPlanEntry

        plan = MealPlan.objects.create(user=user, week_start="2026-11-02")
        MealPlanEntry.objects.create(
            plan=plan,
            day="mon",
            meal_type="dinner",
            dish_id="33333333-3333-3333-3333-333333333333",
            dish_slug="test-dish",
            servings=2,
        )
        response = auth_client.get("/v1/me/export/")
        data = response.json()
        assert len(data["meal_plans"]) == 1
        assert len(data["meal_plans"][0]["entries"]) == 1

    def test_export_with_submissions(self, auth_client, user):
        from apps.community.models import Submission

        Submission.objects.create(user=user, payload={"name": "My Dish"}, status="draft")
        response = auth_client.get("/v1/me/export/")
        data = response.json()
        assert len(data["submissions"]) == 1


# ---------------------------------------------------------------------------
# Tasks — purge except blocks (mock model delete to raise)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPurgeExceptionHandling:
    """Test that each purge block catches exceptions and continues."""

    def _call_task(self, user_id):
        from apps.accounts.tasks import purge_user_data_after_grace_period

        purge_user_data_after_grace_period(user_id=str(user_id))

    def test_purge_continues_when_pantry_delete_fails(self, user, mocker):
        from apps.pantry.models import PantryItem

        PantryItem.objects.create(
            user=user,
            ingredient_id="11111111-1111-1111-1111-111111111111",
            ingredient_slug="tomato",
            display_name="Tomato",
        )
        mocker.patch.object(
            PantryItem.objects,
            "filter",
            side_effect=RuntimeError("DB error"),
        )
        user.soft_delete()
        self._call_task(user.id)
        # Should not raise — error is caught

    def test_purge_continues_when_library_delete_fails(self, user, mocker):
        from apps.library.models import SavedRecipe

        SavedRecipe.objects.create(
            user=user,
            dish_id="22222222-2222-2222-2222-222222222222",
            dish_slug="ugali",
            dataset_version="2026.10.0",
        )
        mocker.patch.object(
            SavedRecipe.objects,
            "filter",
            side_effect=RuntimeError("DB error"),
        )
        user.soft_delete()
        self._call_task(user.id)

    def test_purge_continues_when_planner_delete_fails(self, user, mocker):
        from apps.planner.models import MealPlan

        MealPlan.objects.create(user=user, week_start="2026-11-02")
        mocker.patch.object(
            MealPlan.objects,
            "filter",
            side_effect=RuntimeError("DB error"),
        )
        user.soft_delete()
        self._call_task(user.id)

    def test_purge_continues_when_community_delete_fails(self, user, mocker):
        from apps.community.models import Submission

        Submission.objects.create(user=user, payload={"name": "Test"})
        mocker.patch.object(
            Submission.objects,
            "filter",
            side_effect=RuntimeError("DB error"),
        )
        user.soft_delete()
        self._call_task(user.id)

    def test_purge_continues_when_notifications_delete_fails(self, user, mocker):
        from apps.notifications.models import Notification

        Notification.objects.create(user=user, title="Test", body="Body")
        mocker.patch.object(
            Notification.objects,
            "filter",
            side_effect=RuntimeError("DB error"),
        )
        user.soft_delete()
        self._call_task(user.id)

    def test_purge_continues_when_devices_delete_fails(self, user, mocker):
        from apps.accounts.models import Device

        Device.objects.create(user=user, platform="android", push_token="tok")
        mocker.patch.object(
            Device.objects,
            "filter",
            side_effect=RuntimeError("DB error"),
        )
        user.soft_delete()
        self._call_task(user.id)

    def test_purge_continues_when_email_verifications_delete_fails(self, user, mocker):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import EmailVerification

        EmailVerification.objects.create(
            user=user,
            token="abc",
            expires_at=timezone.now() + timedelta(hours=24),
        )
        mocker.patch.object(
            EmailVerification.objects,
            "filter",
            side_effect=RuntimeError("DB error"),
        )
        user.soft_delete()
        self._call_task(user.id)

    def test_purge_continues_when_profile_delete_fails(self, user, mocker):
        from apps.profiles.models import Profile

        Profile.objects.create(user=user, household_size=3)
        mocker.patch.object(
            Profile.objects,
            "filter",
            side_effect=RuntimeError("DB error"),
        )
        user.soft_delete()
        self._call_task(user.id)

    def test_purge_continues_when_billing_delete_fails(self, user, mocker):
        from apps.billing.models import Plan, Subscription

        plan = Plan.objects.create(code="plus", name="Plus", price_kes="199.00", features=[])
        Subscription.objects.create(user=user, plan=plan, status=Subscription.Status.ACTIVE)
        mocker.patch.object(
            Subscription.objects,
            "filter",
            side_effect=RuntimeError("DB error"),
        )
        user.soft_delete()
        self._call_task(user.id)
