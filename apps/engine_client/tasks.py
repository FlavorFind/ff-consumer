"""Celery tasks for the engine_client app."""

import logging

from celery import shared_task
from django.core.cache import cache

logger = logging.getLogger(__name__)


@shared_task(name="apps.engine_client.tasks.check_dataset_drift")
def check_dataset_drift():
    """Nightly task: check if the engine dataset version has changed.

    If it has, flush engine caches and queue a drift check for saved recipes.
    """
    from apps.engine_client.client import engine

    try:
        # Get currently cached version before refresh
        cached_version = cache.get("ffconsumer:engine:dataset_version", "unknown")
        new_version = engine.refresh_dataset_version()

        if cached_version != "unknown" and cached_version != new_version:
            logger.info(
                "Dataset version changed: %s → %s. Flushing engine caches.",
                cached_version,
                new_version,
            )
            # Per-version cache keys will naturally miss and be re-filled.
            # Trigger saved recipe drift check.
            from apps.core.tasks import check_dataset_drift_saved_recipes

            check_dataset_drift_saved_recipes.delay(new_version, cached_version)
        else:
            logger.info("Dataset version unchanged: %s", new_version)

    except Exception as exc:
        logger.error("Dataset drift check failed: %s", exc)
