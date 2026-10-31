"""
Root conftest.py — pytest-django configuration and shared fixtures.

DJANGO_SETTINGS_MODULE is declared in pyproject.toml [tool.pytest.ini_options].
"""

import os

import pytest


def pytest_configure(config):
    """Called by pytest before collection begins."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
    os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
    os.environ.setdefault(
        "DATABASE_URL",
        "postgres://ff_consumer:ff_consumer_pass@localhost:5432/ff_consumer_test",
    )


@pytest.fixture
def api_client():
    """A DRF APIClient instance."""
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def user(db):
    """A basic active user."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(
        email="test@example.com",
        password="testpass123",
        status=User.Status.ACTIVE,
    )


@pytest.fixture
def auth_client(api_client, user):
    """An APIClient authenticated as `user`."""
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client


@pytest.fixture
def other_user(db):
    """A second user — for permission tests."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(
        email="other@example.com",
        password="otherpass123",
        status=User.Status.ACTIVE,
    )


@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    """Clear the Django cache before and after each test.

    Prevents cached engine responses (dataset version, search results) from
    leaking between tests and causing false positives or missed HTTP calls.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def patch_celery_tasks(mocker):
    """Patch all Celery task dispatching so tests never need a real broker.

    Tasks that are dispatched with .delay() or .apply_async() in views/models
    are replaced with no-ops. Tests that want to verify a task was dispatched
    can inspect the mock; tests that want to test task *logic* call the task
    function directly.
    """
    try:
        mocker.patch("apps.core.tasks.ship_audit_event.delay", return_value=None)
        mocker.patch("apps.core.tasks.ship_audit_event.apply_async", return_value=None)
        mocker.patch(
            "apps.accounts.tasks.purge_user_data_after_grace_period.delay", return_value=None
        )
        mocker.patch(
            "apps.accounts.tasks.purge_user_data_after_grace_period.apply_async",
            return_value=None,
        )
    except Exception:
        # mocker not available (pytest-mock not installed) — skip patching
        pass
