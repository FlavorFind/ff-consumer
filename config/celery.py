"""Celery application for ff-consumer."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("ff_consumer")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
