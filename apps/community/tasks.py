"""Community Celery tasks — forward approved submissions to the engine."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="apps.community.tasks.forward_submission_to_engine",
    max_retries=3,
    default_retry_delay=120,
)
def forward_submission_to_engine(submission_id: str):
    """Forward an approved community submission to the engine.

    Called by the moderation app after a moderator approves a submission.
    Uses the ENGINE_INTERNAL_KEY (internal:curation scope).
    """
    from apps.community.models import Submission
    from apps.engine_client.client import engine

    try:
        submission = Submission.objects.get(id=submission_id)
    except Submission.DoesNotExist:
        logger.error("Submission %s not found — cannot forward to engine.", submission_id)
        return

    if submission.status != Submission.Status.DRAFT:
        logger.info(
            "Submission %s is in status %s — skipping forward.",
            submission_id,
            submission.status,
        )
        return

    try:
        result = engine.submit_community(submission.payload)
        engine_id = result.get("id") or result.get("submission_id")
        submission.engine_submission_id = engine_id
        submission.status = Submission.Status.SENT
        submission.save(update_fields=["engine_submission_id", "status", "updated_at"])
        logger.info(
            "Submission %s forwarded to engine as %s.", submission_id, engine_id
        )
    except Exception as exc:
        logger.error("Failed to forward submission %s: %s", submission_id, exc)
        raise
