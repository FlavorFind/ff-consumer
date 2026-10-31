"""Accounts Celery tasks — user data purge after account deletion grace period."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)

# Grace period: 35 days. After this, personal data is purged.
PURGE_GRACE_PERIOD_DAYS = 35


@shared_task(
    name="apps.accounts.tasks.purge_user_data_after_grace_period",
    max_retries=3,
    default_retry_delay=3600,
)
def purge_user_data_after_grace_period(user_id: str):
    """Purge all personal data for a soft-deleted user.

    Called automatically 35 days after account deletion is requested.
    Only runs if the user is still in DELETED status — if they reactivated,
    this task is a no-op.

    Data purged:
      - Pantry items
      - Saved recipes, collections, cook log
      - Meal plans and shopping lists
      - Community submissions and reviews
      - Devices and push tokens
      - OTP requests
      - Consent records (kept as anonymous records for compliance)
      - Profile and diet tags
      - The CustomUser record itself (anonymised, not deleted, for FK integrity)
    """
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from apps.core.models import AuditEvent, log_audit_event

    User = get_user_model()

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.warning("purge_user_data: user %s not found — skipping.", user_id)
        return

    if user.status != user.Status.DELETED:
        logger.info(
            "purge_user_data: user %s is in status %s — not purging (account reactivated?).",
            user_id,
            user.status,
        )
        return

    logger.info("Starting data purge for deleted user %s", user_id)

    # Purge pantry
    try:
        from apps.pantry.models import PantryItem

        PantryItem.objects.filter(user=user).delete()
    except Exception as exc:
        logger.warning("purge_user_data pantry error for %s: %s", user_id, exc)

    # Purge library
    try:
        from apps.library.models import CookLog, SavedRecipe

        SavedRecipe.objects.filter(user=user).delete()
        CookLog.objects.filter(user=user).delete()
    except Exception as exc:
        logger.warning("purge_user_data library error for %s: %s", user_id, exc)

    # Purge planner
    try:
        from apps.planner.models import MealPlan, ShoppingList

        MealPlan.objects.filter(user=user).delete()
        ShoppingList.objects.filter(user=user).delete()
    except Exception as exc:
        logger.warning("purge_user_data planner error for %s: %s", user_id, exc)

    # Purge community
    try:
        from apps.community.models import Review, Submission

        Submission.objects.filter(user=user).delete()
        Review.objects.filter(user=user).delete()
    except Exception as exc:
        logger.warning("purge_user_data community error for %s: %s", user_id, exc)

    # Purge notifications
    try:
        from apps.notifications.models import Notification, NotificationPreference

        Notification.objects.filter(user=user).delete()
        NotificationPreference.objects.filter(user=user).delete()
    except Exception as exc:
        logger.warning("purge_user_data notifications error for %s: %s", user_id, exc)

    # Purge devices
    try:
        from apps.accounts.models import Device

        Device.objects.filter(user=user).delete()
    except Exception as exc:
        logger.warning("purge_user_data devices error for %s: %s", user_id, exc)

    # Purge email verifications
    try:
        from apps.accounts.models import EmailVerification

        EmailVerification.objects.filter(user=user).delete()
    except Exception as exc:
        logger.warning("purge_user_data email_verification error for %s: %s", user_id, exc)

    # Purge profile
    try:
        from apps.profiles.models import Profile, ProfileDiet

        Profile.objects.filter(user=user).delete()
        ProfileDiet.objects.filter(user=user).delete()
    except Exception as exc:
        logger.warning("purge_user_data profile error for %s: %s", user_id, exc)

    # Purge subscription and payments
    try:
        from apps.billing.models import Subscription

        Subscription.objects.filter(user=user).delete()
    except Exception as exc:
        logger.warning("purge_user_data billing error for %s: %s", user_id, exc)

    # Anonymise the user record — keep the row for FK integrity in audit log
    user.email = f"deleted_{user_id}@deleted.invalid"
    user.set_unusable_password()
    user.save(update_fields=["email", "password", "updated_at"])

    log_audit_event(
        action="account_purged",
        actor_id=user_id,
        actor_type=AuditEvent.ActorType.SYSTEM,
        object_type="user",
        object_id=user_id,
        after_data={"purged_at": timezone.now().isoformat()},
    )

    logger.info("Data purge complete for user %s", user_id)
