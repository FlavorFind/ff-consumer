"""Base models shared across all apps."""

import uuid

from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base with UUID pk, created_at and updated_at."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(TimeStampedModel):
    """Abstract base that adds soft-delete support."""

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class AuditEvent(models.Model):
    """Append-only audit log for sensitive actions.

    Never update or delete records from this table.
    Records are shipped to an external log store via Celery task.
    """

    class ActorType(models.TextChoices):
        USER = "user", "End User"
        STAFF = "staff", "Staff"
        SYSTEM = "system", "System"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_id = models.UUIDField(null=True, blank=True, db_index=True)
    actor_type = models.CharField(
        max_length=10, choices=ActorType.choices, default=ActorType.USER
    )
    action = models.CharField(
        max_length=100,
        db_index=True,
        help_text="e.g. delete_account, approve_submission, payment_confirmed",
    )
    object_type = models.CharField(max_length=100, blank=True, default="")
    object_id = models.UUIDField(null=True, blank=True)
    before_data = models.JSONField(null=True, blank=True)
    after_data = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "audit event"
        verbose_name_plural = "audit events"
        ordering = ["-created_at"]
        # Append-only — no update or delete
        default_permissions = ("add", "view")

    def __str__(self):
        return f"{self.actor_type}:{self.actor_id} — {self.action} at {self.created_at}"


def log_audit_event(
    action: str,
    actor_id=None,
    actor_type: str = AuditEvent.ActorType.USER,
    object_type: str = "",
    object_id=None,
    before_data=None,
    after_data=None,
    reason: str = "",
    ip_address: str | None = None,
):
    """Create an audit event record and queue it for shipping.

    Use this function instead of creating AuditEvent directly.
    """
    event = AuditEvent.objects.create(
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        object_type=object_type,
        object_id=object_id,
        before_data=before_data,
        after_data=after_data,
        reason=reason,
        ip_address=ip_address,
    )
    # Ship to external log store asynchronously
    from apps.core.tasks import ship_audit_event

    ship_audit_event.delay(str(event.id))
    return event
