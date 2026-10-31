"""Test settings — fast, isolated, no external services."""

import os

# Set required env vars before base settings are imported.
# DATABASE_URL: use SQLite by default so tests run without a running Postgres.
# In CI, set DATABASE_URL to a real Postgres URL for full fidelity.
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-do-not-use")
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/ff_consumer_test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from .base import *  # noqa: F401, F403

DEBUG = False

# Fast password hasher in tests
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Disable Sentry in tests
SENTRY_DSN = ""

# In-memory cache — no Redis needed for local tests
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Celery runs tasks synchronously in tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

LOGGING["root"]["level"] = "WARNING"  # noqa: F405

# Engine client: use mock URL in tests (override per test with responses library)
ENGINE_BASE_URL = "http://engine.test"
ENGINE_API_KEY = "ffk_test_0000000000000000000000000000000000000000"
ENGINE_INTERNAL_KEY = "ffk_internal_test_000000000000000000000000000000000000000"
