"""Community models — recipe submissions and dish reviews."""

import uuid

from django.conf import settings
from django.db import models


class Submission(models.Model):
    """A user-submitted recipe draft.

    Flow: draft → (moderation) → sent → (engine processes) → in_review → accepted|rejected
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent to Engine"
        IN_REVIEW = "in_review", "In Review"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submissions"
    )
    # Raw submission payload — validated required fields at creation time
    payload = models.JSONField()
    # Set after the Celery worker forwards to engine
    engine_submission_id = models.UUIDField(null=True, blank=True, db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "submission"
        verbose_name_plural = "submissions"

    def __str__(self):
        name = self.payload.get("name_en", "unnamed")
        return f"{self.user} — {name} ({self.status})"


class Review(models.Model):
    """A user review of a dish (1–5 stars + text).

    Goes through moderation before becoming visible.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews"
    )
    dish_id = models.CharField(max_length=36, db_index=True)  # engine UUID
    dish_slug = models.CharField(max_length=200)
    stars = models.IntegerField()  # 1–5
    text = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        # One review per user per dish
        unique_together = [("user", "dish_id")]

    def __str__(self):
        return f"{self.user} — {self.dish_slug} {self.stars}★"
