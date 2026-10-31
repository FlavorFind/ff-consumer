"""Billing Celery tasks — renewal reminders, expiry checks."""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="apps.billing.tasks.check_subscription_expiry")
def check_subscription_expiry():
    """Daily task: expire subscriptions whose renews_at has passed."""
    from apps.billing.models import Subscription

    now = timezone.now()
    expired = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        renews_at__lt=now,
    )
    count = expired.update(status=Subscription.Status.EXPIRED)
    if count:
        logger.info("Expired %d subscription(s).", count)


@shared_task(name="apps.billing.tasks.check_trial_expiry")
def check_trial_expiry():
    """Daily task: expire trials whose trial_ends_at has passed."""
    from apps.billing.models import Subscription

    now = timezone.now()
    expired_trials = Subscription.objects.filter(
        status=Subscription.Status.TRIALING,
        trial_ends_at__lt=now,
    )
    count = expired_trials.update(status=Subscription.Status.EXPIRED)
    if count:
        logger.info("Expired %d trial(s).", count)


@shared_task(name="apps.billing.tasks.send_renewal_reminders")
def send_renewal_reminders():
    """Daily task: notify users whose subscription renews in 3 days."""
    from apps.billing.models import Subscription

    now = timezone.now()
    reminder_date = now + timedelta(days=3)
    upcoming = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        renews_at__date=reminder_date.date(),
    ).select_related("user")

    for sub in upcoming:
        logger.info(
            "Renewal reminder for user %s — renews at %s", sub.user_id, sub.renews_at
        )
        # TODO: trigger push notification / email via notifications app
