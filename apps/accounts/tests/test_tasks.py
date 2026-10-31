"""Tests for accounts/tasks.py — user data purge after account deletion."""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestPurgeUserDataAfterGracePeriod:
    """Tests for purge_user_data_after_grace_period Celery task."""

    def _call_task(self, user_id):
        """Call the task function directly (not via Celery)."""
        from apps.accounts.tasks import purge_user_data_after_grace_period

        purge_user_data_after_grace_period(user_id=str(user_id))

    def test_purge_nonexistent_user_is_noop(self):
        """If the user doesn't exist, the task should log a warning and return."""
        self._call_task("00000000-0000-0000-0000-000000000000")
        # No exception raised — that's the assertion

    def test_purge_active_user_is_noop(self, user):
        """If the user is not in DELETED status, the task should not purge."""
        from apps.pantry.models import PantryItem

        PantryItem.objects.create(
            user=user,
            ingredient_id="11111111-1111-1111-1111-111111111111",
            ingredient_slug="tomato",
            display_name="Tomato",
        )

        self._call_task(user.id)

        # Pantry item should still exist
        assert PantryItem.objects.filter(user=user).exists()

    def test_purge_deleted_user_removes_pantry(self, user):
        """Pantry items are deleted when user is purged."""
        from apps.pantry.models import PantryItem

        PantryItem.objects.create(
            user=user,
            ingredient_id="11111111-1111-1111-1111-111111111111",
            ingredient_slug="tomato",
            display_name="Tomato",
        )
        user.soft_delete()

        self._call_task(user.id)

        assert not PantryItem.objects.filter(user_id=user.id).exists()

    def test_purge_deleted_user_removes_library(self, user):
        """Saved recipes and cook logs are deleted when user is purged."""
        from apps.library.models import CookLog, SavedRecipe

        SavedRecipe.objects.create(
            user=user,
            dish_id="22222222-2222-2222-2222-222222222222",
            dish_slug="ugali-sukuma",
            dataset_version="2026.10.0",
        )
        CookLog.objects.create(user=user, dish_id="22222222-2222-2222-2222-222222222222")
        user.soft_delete()

        self._call_task(user.id)

        assert not SavedRecipe.objects.filter(user_id=user.id).exists()
        assert not CookLog.objects.filter(user_id=user.id).exists()

    def test_purge_deleted_user_removes_planner(self, user):
        """Meal plans and shopping lists are deleted when user is purged."""
        from apps.planner.models import MealPlan, ShoppingList

        plan = MealPlan.objects.create(user=user, week_start="2026-11-02")
        ShoppingList.objects.create(user=user, plan=plan)
        user.soft_delete()

        self._call_task(user.id)

        assert not MealPlan.objects.filter(user_id=user.id).exists()
        assert not ShoppingList.objects.filter(user_id=user.id).exists()

    def test_purge_deleted_user_removes_community(self, user):
        """Submissions and reviews are deleted when user is purged."""
        from apps.community.models import Review, Submission

        Submission.objects.create(user=user, payload={"name": "Test Dish"})
        Review.objects.create(
            user=user,
            dish_id="33333333-3333-3333-3333-333333333333",
            dish_slug="test-dish",
            stars=5,
            text="Great!",
        )
        user.soft_delete()

        self._call_task(user.id)

        assert not Submission.objects.filter(user_id=user.id).exists()
        assert not Review.objects.filter(user_id=user.id).exists()

    def test_purge_deleted_user_removes_notifications(self, user):
        """Notifications and preferences are deleted when user is purged."""
        from apps.notifications.models import Notification, NotificationPreference

        NotificationPreference.objects.create(user=user)
        Notification.objects.create(user=user, title="Test", body="Test body")
        user.soft_delete()

        self._call_task(user.id)

        assert not Notification.objects.filter(user_id=user.id).exists()
        assert not NotificationPreference.objects.filter(user_id=user.id).exists()

    def test_purge_deleted_user_removes_devices(self, user):
        """Devices are deleted when user is purged."""
        from apps.accounts.models import Device

        Device.objects.create(user=user, platform="android", push_token="token123")
        user.soft_delete()

        self._call_task(user.id)

        assert not Device.objects.filter(user_id=user.id).exists()

    def test_purge_deleted_user_removes_email_verifications(self, user):
        """Email verifications are deleted when user is purged."""
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import EmailVerification

        EmailVerification.objects.create(
            user=user,
            token="abcdef1234567890",
            expires_at=timezone.now() + timedelta(hours=24),
        )
        user.soft_delete()

        self._call_task(user.id)

        assert not EmailVerification.objects.filter(user_id=user.id).exists()

    def test_purge_deleted_user_removes_profile(self, user):
        """Profile and diet tags are deleted when user is purged."""
        from apps.profiles.models import Profile, ProfileDiet

        Profile.objects.create(user=user, household_size=4)
        ProfileDiet.objects.create(user=user, diet_tag_slug="vegetarian")
        user.soft_delete()

        self._call_task(user.id)

        assert not Profile.objects.filter(user_id=user.id).exists()
        assert not ProfileDiet.objects.filter(user_id=user.id).exists()

    def test_purge_deleted_user_removes_subscription(self, user):
        """Subscriptions are deleted when user is purged."""
        from apps.billing.models import Plan, Subscription

        plan = Plan.objects.create(code="plus", name="Plus", price_kes="199.00", features=[])
        Subscription.objects.create(user=user, plan=plan, status=Subscription.Status.ACTIVE)
        user.soft_delete()

        self._call_task(user.id)

        assert not Subscription.objects.filter(user_id=user.id).exists()

    def test_purge_anonymises_user_record(self, user):
        """The user record is anonymised (not hard-deleted) for FK integrity."""
        user.soft_delete()
        original_id = user.id
        original_email = user.email

        self._call_task(user.id)

        user.refresh_from_db()
        # User row still exists
        assert User.objects.filter(id=original_id).exists()
        # Email is anonymised
        assert user.email != original_email
        assert "deleted" in user.email
        # Password is unusable
        assert not user.has_usable_password()

    def test_purge_logs_audit_event(self, user):
        """An audit event is logged when user data is purged."""
        from apps.core.models import AuditEvent

        user.soft_delete()

        self._call_task(user.id)

        assert AuditEvent.objects.filter(
            action="account_purged",
            object_id=user.id,
        ).exists()

    def test_purge_full_flow_all_data_removed(self, user):
        """End-to-end: create user with all data types, purge, verify everything gone."""
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import Device, EmailVerification
        from apps.billing.models import Plan, Subscription
        from apps.community.models import Review, Submission
        from apps.library.models import CookLog, SavedRecipe
        from apps.notifications.models import Notification, NotificationPreference
        from apps.pantry.models import PantryItem
        from apps.planner.models import MealPlan, ShoppingList
        from apps.profiles.models import Profile, ProfileDiet

        # Create all data types
        PantryItem.objects.create(
            user=user,
            ingredient_id="11111111-1111-1111-1111-111111111111",
            ingredient_slug="tomato",
            display_name="Tomato",
        )
        SavedRecipe.objects.create(
            user=user,
            dish_id="22222222-2222-2222-2222-222222222222",
            dish_slug="ugali-sukuma",
            dataset_version="2026.10.0",
        )
        CookLog.objects.create(user=user, dish_id="22222222-2222-2222-2222-222222222222")
        plan = MealPlan.objects.create(user=user, week_start="2026-11-02")
        ShoppingList.objects.create(user=user, plan=plan)
        Submission.objects.create(user=user, payload={"name": "Test"})
        Review.objects.create(
            user=user,
            dish_id="33333333-3333-3333-3333-333333333333",
            dish_slug="test",
            stars=4,
            text="Good",
        )
        NotificationPreference.objects.create(user=user)
        Notification.objects.create(user=user, title="Hi", body="Test")
        Device.objects.create(user=user, platform="android", push_token="tok")
        EmailVerification.objects.create(
            user=user,
            token="abc123",
            expires_at=timezone.now() + timedelta(hours=24),
        )
        Profile.objects.create(user=user, household_size=3)
        ProfileDiet.objects.create(user=user, diet_tag_slug="halal")
        plus_plan = Plan.objects.create(code="plus", name="Plus", price_kes="199.00", features=[])
        Subscription.objects.create(user=user, plan=plus_plan, status=Subscription.Status.ACTIVE)

        # Soft delete and purge
        user.soft_delete()
        self._call_task(user.id)

        # Everything should be gone
        assert not PantryItem.objects.filter(user_id=user.id).exists()
        assert not SavedRecipe.objects.filter(user_id=user.id).exists()
        assert not CookLog.objects.filter(user_id=user.id).exists()
        assert not MealPlan.objects.filter(user_id=user.id).exists()
        assert not ShoppingList.objects.filter(user_id=user.id).exists()
        assert not Submission.objects.filter(user_id=user.id).exists()
        assert not Review.objects.filter(user_id=user.id).exists()
        assert not Notification.objects.filter(user_id=user.id).exists()
        assert not NotificationPreference.objects.filter(user_id=user.id).exists()
        assert not Device.objects.filter(user_id=user.id).exists()
        assert not EmailVerification.objects.filter(user_id=user.id).exists()
        assert not Profile.objects.filter(user_id=user.id).exists()
        assert not ProfileDiet.objects.filter(user_id=user.id).exists()
        assert not Subscription.objects.filter(user_id=user.id).exists()
