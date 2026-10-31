"""Core Celery tasks — audit log shipping, dataset drift check."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="apps.core.tasks.ship_audit_event", max_retries=3, default_retry_delay=60)
def ship_audit_event(event_id: str):
    """Ship an audit event to the external log store.

    In v1, this logs to the structured logger (picked up by log aggregation).
    Replace with a real external store (e.g. BigQuery, S3, Splunk) in production.
    """
    from apps.core.models import AuditEvent

    try:
        event = AuditEvent.objects.get(id=event_id)
        logger.info(
            "AUDIT_EVENT action=%s actor_type=%s actor_id=%s object_type=%s object_id=%s",
            event.action,
            event.actor_type,
            event.actor_id,
            event.object_type,
            event.object_id,
            extra={
                "audit_event_id": str(event.id),
                "audit_action": event.action,
                "audit_actor_type": event.actor_type,
                "audit_actor_id": str(event.actor_id) if event.actor_id else None,
                "audit_object_type": event.object_type,
                "audit_object_id": str(event.object_id) if event.object_id else None,
                "audit_created_at": event.created_at.isoformat(),
            },
        )
    except Exception as exc:
        logger.error("Failed to ship audit event %s: %s", event_id, exc)
        raise


@shared_task(name="apps.core.tasks.check_dataset_drift_saved_recipes")
def check_dataset_drift_saved_recipes(new_version: str, old_version: str):
    """Compare saved recipe dataset_versions against the new engine version.

    Flags recipes that were saved under the old version so the app can
    surface a "this recipe may have changed" notice.

    In v1: logs the count. In a future version, set a `drift_flagged` field
    or call the engine's dataset diff endpoint.
    """
    from apps.library.models import SavedRecipe

    stale_count = SavedRecipe.objects.exclude(dataset_version=new_version).count()
    logger.info(
        "Dataset version changed %s → %s. Stale saved recipes: %d",
        old_version,
        new_version,
        stale_count,
    )
