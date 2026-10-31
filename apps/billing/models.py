"""Billing models — Plans, Subscriptions, Payments."""

import uuid

from django.conf import settings
from django.db import models


class Plan(models.Model):
    """A billing plan (Free or Plus).

    The `code` is the PK — always "free" or "plus" in v1.
    Records are seeded via `manage.py seed_plans`.
    """

    code = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=100)
    price_kes = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # JSON list of feature keys, e.g. ["meal_plans", "shopping_lists", "offline_sync"]
    features = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "plan"
        verbose_name_plural = "plans"

    def __str__(self):
        return f"{self.name} (KES {self.price_kes}/month)"


class Subscription(models.Model):
    """A user's subscription to a plan.

    One active subscription per user (enforced by unique_together on user).
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        TRIALING = "trialing", "Trialing"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    renews_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "subscription"
        verbose_name_plural = "subscriptions"

    def __str__(self):
        return f"{self.user} — {self.plan_id} ({self.status})"

    def is_active_plus(self) -> bool:
        """True if the user has an active or trialing Plus subscription."""
        return (
            self.plan_id == "plus"
            and self.status in (self.Status.ACTIVE, self.Status.TRIALING)
        )


class Payment(models.Model):
    """A payment record for a subscription.

    provider_ref is the M-Pesa transaction ID — used as idempotency key.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="payments"
    )
    provider = models.CharField(max_length=20, default="mpesa")
    # M-Pesa transaction ID — unique idempotency key
    provider_ref = models.CharField(max_length=100, unique=True)
    # Amount re-verified server-side — never trust the callback amount alone
    amount_kes = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    receipt_no = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "payment"
        verbose_name_plural = "payments"

    def __str__(self):
        return f"{self.user} — KES {self.amount_kes} ({self.status})"
