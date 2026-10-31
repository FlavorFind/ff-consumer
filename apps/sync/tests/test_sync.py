"""Sync app tests — push and pull endpoints."""

import pytest
import responses as rsps

ENGINE = "http://engine.test"


@pytest.fixture
def plus_user(db):
    from django.contrib.auth import get_user_model

    from apps.billing.models import Plan, Subscription

    User = get_user_model()
    user = User.objects.create_user(
        email="sync_plus@example.com",
        username="syncplus",
        password="testpass",
        status=User.Status.ACTIVE,
    )
    plan, _ = Plan.objects.get_or_create(
        code="plus",
        defaults={"name": "Flavor Find Plus", "price_kes": 199},
    )
    Subscription.objects.create(user=user, plan=plan, status="active")
    return user


@pytest.fixture
def plus_client(plus_user):
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    refresh = RefreshToken.for_user(plus_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


@pytest.mark.django_db
class TestSyncPushView:
    def test_push_empty_changes(self, plus_client):
        response = plus_client.post("/v1/sync/push/", {"changes": []}, format="json")
        assert response.status_code == 200
        data = response.json()
        assert data["applied"] == []
        assert data["conflicts"] == []
        assert "server_time" in data

    def test_push_create_pantry_item(self, plus_client):
        import uuid

        change_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        response = plus_client.post(
            "/v1/sync/push/",
            {
                "changes": [
                    {
                        "change_id": change_id,
                        "changed_at": "2026-10-31T10:00:00Z",
                        "entity_type": "pantry_item",
                        "entity_id": entity_id,
                        "operation": "create",
                        "payload": {
                            "ingredient_id": "i001",
                            "ingredient_slug": "sukuma",
                            "display_name": "Sukuma wiki",
                        },
                    }
                ]
            },
            format="json",
        )
        assert response.status_code == 200
        assert change_id in response.json()["applied"]

        from apps.pantry.models import PantryItem

        assert PantryItem.objects.filter(id=entity_id).exists()

    def test_push_delete_pantry_item(self, plus_client, plus_user):
        import uuid

        from apps.pantry.models import PantryItem

        entity_id = uuid.uuid4()
        PantryItem.objects.create(
            id=entity_id,
            user=plus_user,
            ingredient_id="i001",
            ingredient_slug="sukuma",
            display_name="Sukuma wiki",
        )

        change_id = str(uuid.uuid4())
        response = plus_client.post(
            "/v1/sync/push/",
            {
                "changes": [
                    {
                        "change_id": change_id,
                        "changed_at": "2026-10-31T10:00:00Z",
                        "entity_type": "pantry_item",
                        "entity_id": str(entity_id),
                        "operation": "delete",
                        "payload": {},
                    }
                ]
            },
            format="json",
        )
        assert response.status_code == 200
        assert not PantryItem.objects.filter(id=entity_id).exists()

    def test_push_create_cook_log(self, plus_client):
        import uuid

        change_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        response = plus_client.post(
            "/v1/sync/push/",
            {
                "changes": [
                    {
                        "change_id": change_id,
                        "changed_at": "2026-10-31T10:00:00Z",
                        "entity_type": "cook_log",
                        "entity_id": entity_id,
                        "operation": "create",
                        "payload": {
                            "dish_id": "d001",
                            "dish_slug": "ugali",
                            "rating": 5,
                        },
                    }
                ]
            },
            format="json",
        )
        assert response.status_code == 200
        assert change_id in response.json()["applied"]

        from apps.library.models import CookLog

        assert CookLog.objects.filter(id=entity_id).exists()

    @rsps.activate
    def test_push_create_saved_recipe(self, plus_client):
        import uuid

        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )

        change_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        response = plus_client.post(
            "/v1/sync/push/",
            {
                "changes": [
                    {
                        "change_id": change_id,
                        "changed_at": "2026-10-31T10:00:00Z",
                        "entity_type": "saved_recipe",
                        "entity_id": entity_id,
                        "operation": "create",
                        "payload": {
                            "dish_id": "d001",
                            "dish_slug": "ugali",
                        },
                    }
                ]
            },
            format="json",
        )
        assert response.status_code == 200
        assert change_id in response.json()["applied"]

    def test_push_update_shopping_item_checked(self, plus_client, plus_user):
        import uuid

        from apps.planner.models import MealPlan, ShoppingItem, ShoppingList

        plan = MealPlan.objects.create(user=plus_user, week_start="2026-10-26")
        sl = ShoppingList.objects.create(user=plus_user, plan=plan, name="Week")
        item = ShoppingItem.objects.create(
            shopping_list=sl,
            ingredient_id="i001",
            ingredient_slug="sukuma",
            display_name="Sukuma wiki",
            position=0,
        )

        change_id = str(uuid.uuid4())
        response = plus_client.post(
            "/v1/sync/push/",
            {
                "changes": [
                    {
                        "change_id": change_id,
                        "changed_at": "2026-10-31T10:00:00Z",
                        "entity_type": "shopping_item",
                        "entity_id": str(item.id),
                        "operation": "update",
                        "payload": {"checked": True},
                    }
                ]
            },
            format="json",
        )
        assert response.status_code == 200
        item.refresh_from_db()
        assert item.checked is True

    def test_push_meal_plan_entry_ignored(self, plus_client):
        """meal_plan_entry changes from client are silently ignored (server wins)."""
        import uuid

        change_id = str(uuid.uuid4())
        response = plus_client.post(
            "/v1/sync/push/",
            {
                "changes": [
                    {
                        "change_id": change_id,
                        "changed_at": "2026-10-31T10:00:00Z",
                        "entity_type": "meal_plan_entry",
                        "entity_id": str(uuid.uuid4()),
                        "operation": "create",
                        "payload": {},
                    }
                ]
            },
            format="json",
        )
        # Applied (not conflicted) — server simply ignores it
        assert response.status_code == 200
        assert change_id in response.json()["applied"]

    def test_push_requires_plus(self, auth_client):
        assert auth_client.post("/v1/sync/push/", {"changes": []}, format="json").status_code == 403


@pytest.mark.django_db
class TestSyncPullView:
    def test_pull_no_since_returns_all(self, plus_client, plus_user):
        from apps.pantry.models import PantryItem

        PantryItem.objects.create(
            user=plus_user,
            ingredient_id="i001",
            ingredient_slug="sukuma",
            display_name="Sukuma wiki",
        )

        response = plus_client.get("/v1/sync/pull/")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1
        assert "server_time" in data

    def test_pull_with_since_filters(self, plus_client, plus_user):
        """Changes before the since timestamp should not be returned."""
        from apps.pantry.models import PantryItem

        PantryItem.objects.create(
            user=plus_user,
            ingredient_id="i001",
            ingredient_slug="sukuma",
            display_name="Sukuma wiki",
        )

        # Use a future timestamp — should return nothing
        response = plus_client.get("/v1/sync/pull/?since=2099-01-01T00:00:00Z")
        assert response.status_code == 200
        assert response.json()["count"] == 0

    def test_pull_invalid_since(self, plus_client):
        response = plus_client.get("/v1/sync/pull/?since=not-a-date")
        assert response.status_code == 400

    def test_pull_requires_plus(self, auth_client):
        assert auth_client.get("/v1/sync/pull/").status_code == 403
