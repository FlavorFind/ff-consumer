"""Notifications app tests."""

import pytest


@pytest.fixture
def notification(db, user):
    from apps.notifications.models import Notification

    return Notification.objects.create(
        user=user,
        channel=Notification.Channel.IN_APP,
        type="meal_reminder",
        title="Time to cook!",
        body="You have ugali planned for dinner.",
    )


@pytest.mark.django_db
class TestNotificationList:
    def test_list_notifications_empty(self, auth_client):
        response = auth_client.get("/v1/notifications/")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_in_app_notifications(self, auth_client, notification):
        response = auth_client.get("/v1/notifications/")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["type"] == "meal_reminder"

    def test_push_notifications_not_listed(self, auth_client, user):
        from apps.notifications.models import Notification

        Notification.objects.create(
            user=user,
            channel=Notification.Channel.PUSH,
            type="push_notif",
            title="Push",
            body="Push body",
        )
        response = auth_client.get("/v1/notifications/")
        # Push notifications don't appear in the in-app list
        assert all(n["channel"] == "in_app" for n in response.json())

    def test_requires_auth(self, api_client):
        assert api_client.get("/v1/notifications/").status_code == 401

    def test_other_users_notifications_not_visible(self, auth_client, other_user):
        from apps.notifications.models import Notification

        Notification.objects.create(
            user=other_user,
            channel=Notification.Channel.IN_APP,
            type="other",
            title="Other",
            body="Other body",
        )
        response = auth_client.get("/v1/notifications/")
        assert response.json() == []


@pytest.mark.django_db
class TestMarkRead:
    def test_mark_notification_as_read(self, auth_client, notification):
        response = auth_client.post(f"/v1/notifications/{notification.id}/read/")
        assert response.status_code == 200
        assert response.json()["read_at"] is not None

    def test_mark_already_read_is_idempotent(self, auth_client, notification):
        auth_client.post(f"/v1/notifications/{notification.id}/read/")
        first_read_at = auth_client.post(f"/v1/notifications/{notification.id}/read/").json()[
            "read_at"
        ]
        second_read_at = auth_client.post(f"/v1/notifications/{notification.id}/read/").json()[
            "read_at"
        ]
        assert first_read_at == second_read_at

    def test_mark_other_users_notification_returns_404(self, auth_client, other_user):
        from apps.notifications.models import Notification

        other_notif = Notification.objects.create(
            user=other_user, channel=Notification.Channel.IN_APP, type="x", title="x", body="x"
        )
        assert auth_client.post(f"/v1/notifications/{other_notif.id}/read/").status_code == 404


@pytest.mark.django_db
class TestNotificationPreferences:
    def test_get_preferences_creates_defaults(self, auth_client):
        response = auth_client.get("/v1/notifications/preferences/")
        assert response.status_code == 200
        assert response.json()["push_enabled"] is True
        assert response.json()["email_enabled"] is True

    def test_patch_preferences(self, auth_client):
        response = auth_client.patch(
            "/v1/notifications/preferences/",
            {"push_enabled": False, "email_enabled": False},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["push_enabled"] is False

    def test_preferences_require_auth(self, api_client):
        assert api_client.get("/v1/notifications/preferences/").status_code == 401
