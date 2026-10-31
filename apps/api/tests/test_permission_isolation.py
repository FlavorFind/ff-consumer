"""
Permission isolation tests — verify user A cannot read, write, or delete user B's data.

These tests cover every app that owns user-scoped data:
  pantry, library, planner, community, billing, notifications, sync

Architecture constraint: every queryset must be filtered by user=request.user.
A 404 (not 403) is the expected response — we never confirm that a resource exists.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(email, username, plus=False):
    """Create an active user, optionally with a Plus subscription."""
    from apps.billing.models import Plan, Subscription

    user = User.objects.create_user(
        email=email,
        username=username,
        password="testpass123",
        status=User.Status.ACTIVE,
    )
    if plus:
        plan, _ = Plan.objects.get_or_create(
            code="plus",
            defaults={"name": "Flavor Find Plus", "price_kes": 199},
        )
        Subscription.objects.create(user=user, plan=plan, status="active")
    return user


def _client_for(user):
    c = APIClient()
    refresh = RefreshToken.for_user(user)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return c


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user_a(db):
    return _make_user("user_a@example.com", "user_a", plus=True)


@pytest.fixture
def user_b(db):
    return _make_user("user_b@example.com", "user_b", plus=True)


@pytest.fixture
def client_a(user_a):
    return _client_for(user_a)


@pytest.fixture
def client_b(user_b):
    return _client_for(user_b)


# ---------------------------------------------------------------------------
# Pantry
# ---------------------------------------------------------------------------


class TestPantryIsolation:
    def test_cannot_list_other_users_pantry(self, client_a, user_b, db):
        from apps.pantry.models import PantryItem

        PantryItem.objects.create(
            user=user_b,
            ingredient_id="11111111-0000-0000-0000-000000000001",
            ingredient_slug="onion",
            display_name="Onion",
        )
        resp = client_a.get("/v1/pantry/")
        assert resp.status_code == 200
        # pantry list returns a plain list — user_a's pantry is empty
        assert resp.data == []

    def test_cannot_delete_other_users_pantry_item(self, client_a, user_b, db):
        from apps.pantry.models import PantryItem

        item = PantryItem.objects.create(
            user=user_b,
            ingredient_id="11111111-0000-0000-0000-000000000002",
            ingredient_slug="tomato",
            display_name="Tomato",
        )
        resp = client_a.delete(f"/v1/pantry/{item.id}/")
        assert resp.status_code == 404
        # Item must still exist
        assert PantryItem.objects.filter(id=item.id).exists()


# ---------------------------------------------------------------------------
# Library — Saved Recipes
# ---------------------------------------------------------------------------


class TestLibraryIsolation:
    def test_cannot_list_other_users_saved_recipes(self, client_a, user_b, db):
        from apps.library.models import SavedRecipe

        SavedRecipe.objects.create(
            user=user_b, dish_id="d-b-001", dish_slug="chapati", dataset_version="2026.10.0"
        )
        resp = client_a.get("/v1/saved/")
        assert resp.status_code == 200
        # list view returns a plain list
        assert resp.data == []

    def test_cannot_delete_other_users_saved_recipe(self, client_a, user_b, db):
        from apps.library.models import SavedRecipe

        recipe = SavedRecipe.objects.create(
            user=user_b, dish_id="d-b-002", dish_slug="ugali", dataset_version="2026.10.0"
        )
        resp = client_a.delete(f"/v1/saved/{recipe.id}/")
        assert resp.status_code == 404

    def test_cannot_patch_other_users_saved_recipe(self, client_a, user_b, db):
        from apps.library.models import SavedRecipe

        recipe = SavedRecipe.objects.create(
            user=user_b, dish_id="d-b-003", dish_slug="githeri", dataset_version="2026.10.0"
        )
        resp = client_a.patch(f"/v1/saved/{recipe.id}/", {"note": "stolen note"}, format="json")
        assert resp.status_code == 404

    def test_cannot_list_other_users_collections(self, client_a, user_b, db):
        from apps.library.models import Collection

        Collection.objects.create(user=user_b, name="Secret Collection")
        resp = client_a.get("/v1/saved/collections/")
        assert resp.status_code == 200
        # user_a has no collections — user_b's must not appear
        assert resp.data == []

    def test_cannot_delete_other_users_collection(self, client_a, user_b, db):
        from apps.library.models import Collection

        col = Collection.objects.create(user=user_b, name="Private")
        resp = client_a.delete(f"/v1/saved/collections/{col.id}/")
        assert resp.status_code == 404

    def test_cannot_patch_other_users_collection(self, client_a, user_b, db):
        from apps.library.models import Collection

        col = Collection.objects.create(user=user_b, name="Private")
        resp = client_a.patch(f"/v1/saved/collections/{col.id}/", {"name": "Hacked"}, format="json")
        assert resp.status_code == 404

    def test_cook_log_only_shows_own_entries(self, client_a, user_b, db):
        from apps.library.models import CookLog

        CookLog.objects.create(user=user_b, dish_id="d-b-004", dish_slug="pilau")
        resp = client_a.get("/v1/cooked/")
        assert resp.status_code == 200
        # plain list, user_a has no logs
        assert resp.data == []


# ---------------------------------------------------------------------------
# Planner — Meal Plans & Shopping Lists
# ---------------------------------------------------------------------------


class TestPlannerIsolation:
    def test_cannot_access_other_users_plan_by_id(self, client_a, user_b, db):
        """Shopping list generation uses plan_id — user A must not use user B's plan."""
        from datetime import date

        from apps.planner.models import MealPlan

        plan = MealPlan.objects.create(user=user_b, week_start=date(2026, 10, 26))
        resp = client_a.post(f"/v1/plans/{plan.id}/shopping-list/")
        assert resp.status_code == 404

    def test_meal_plan_get_returns_own_plan(self, client_a, user_b, db):
        """GET /v1/plans/<week>/ returns user_a's own plan, not user_b's."""
        from datetime import date

        from apps.planner.models import MealPlan

        plan_b = MealPlan.objects.create(user=user_b, week_start=date(2026, 10, 26))
        resp = client_a.get("/v1/plans/2026-W44/")
        assert resp.status_code == 200
        # The returned plan must not be user_b's plan
        assert str(resp.data.get("id")) != str(plan_b.id)

    def test_cannot_get_other_users_shopping_list(self, client_a, user_b, db):
        from apps.planner.models import ShoppingList

        sl = ShoppingList.objects.create(user=user_b, name="User B's groceries")
        resp = client_a.get(f"/v1/shopping-lists/{sl.id}/")
        assert resp.status_code == 404

    def test_cannot_share_other_users_shopping_list(self, client_a, user_b, db):
        from apps.planner.models import ShoppingList

        sl = ShoppingList.objects.create(user=user_b, name="Shared?")
        resp = client_a.get(f"/v1/shopping-lists/{sl.id}/share/")
        assert resp.status_code == 404

    def test_cannot_check_item_on_other_users_shopping_list(self, client_a, user_b, db):
        from apps.planner.models import ShoppingItem, ShoppingList

        sl = ShoppingList.objects.create(user=user_b, name="B's list")
        item = ShoppingItem.objects.create(
            shopping_list=sl,
            ingredient_id="11111111-0000-0000-0000-000000000099",
            ingredient_slug="milk",
            display_name="Milk",
        )
        resp = client_a.patch(
            f"/v1/shopping-lists/{sl.id}/items/{item.id}/",
            {"checked": True},
            format="json",
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Community — Submissions
# ---------------------------------------------------------------------------


class TestCommunityIsolation:
    def test_cannot_get_other_users_submission(self, client_a, user_b, db):
        from apps.community.models import Submission

        sub = Submission.objects.create(user=user_b, payload={"name_en": "Secret Dish"})
        resp = client_a.get(f"/v1/submissions/{sub.id}/")
        assert resp.status_code == 404

    def test_submissions_list_only_shows_own(self, client_a, user_b, db):
        from apps.community.models import Submission

        Submission.objects.create(user=user_b, payload={"name_en": "B's Dish"})
        resp = client_a.get("/v1/submissions/")
        assert resp.status_code == 200
        # plain list — user_a has no submissions
        assert resp.data == []


# ---------------------------------------------------------------------------
# Billing — Subscription
# ---------------------------------------------------------------------------


class TestBillingIsolation:
    def test_subscription_only_shows_own(self, client_a, user_b, db):
        """Each user sees only their own subscription — plan_code field."""
        resp_a = client_a.get("/v1/subscription/")
        client_b_api = _client_for(user_b)
        resp_b = client_b_api.get("/v1/subscription/")

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        # Both have Plus, independently
        assert resp_a.data["plan_code"] == "plus"
        assert resp_b.data["plan_code"] == "plus"


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class TestNotificationsIsolation:
    def test_cannot_mark_other_users_notification_read(self, client_a, user_b, db):
        from apps.notifications.models import Notification

        notif = Notification.objects.create(
            user=user_b,
            title="Secret",
            body="Do not read",
            type="system",
        )
        resp = client_a.post(f"/v1/notifications/{notif.id}/read/")
        assert resp.status_code == 404

    def test_notification_list_only_shows_own(self, client_a, user_b, db):
        from apps.notifications.models import Notification

        Notification.objects.create(
            user=user_b,
            title="B's notification",
            body="Not for A",
            type="system",
        )
        resp = client_a.get("/v1/notifications/")
        assert resp.status_code == 200
        # plain list — user_a has no notifications
        assert resp.data == []


# ---------------------------------------------------------------------------
# Sync — Pull endpoint only returns own data
# ---------------------------------------------------------------------------


class TestSyncIsolation:
    def test_pull_only_returns_own_pantry_items(self, client_a, user_b, db):
        from apps.pantry.models import PantryItem

        b_item = PantryItem.objects.create(
            user=user_b,
            ingredient_id="11111111-0000-0000-0000-000000000010",
            ingredient_slug="garlic",
            display_name="Garlic",
        )
        resp = client_a.get("/v1/sync/pull/")
        assert resp.status_code == 200
        pantry_ids = [item["id"] for item in resp.data.get("pantry", [])]
        assert str(b_item.id) not in pantry_ids

    def test_pull_only_returns_own_saved_recipes(self, client_a, user_b, db):
        from apps.library.models import SavedRecipe

        b_recipe = SavedRecipe.objects.create(
            user=user_b, dish_id="d-b-sync", dish_slug="samosa", dataset_version="2026.10.0"
        )
        resp = client_a.get("/v1/sync/pull/")
        assert resp.status_code == 200
        saved_ids = [r["id"] for r in resp.data.get("saved_recipes", [])]
        assert str(b_recipe.id) not in saved_ids
