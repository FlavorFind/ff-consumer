"""Planner app tests — meal plans, shopping lists, services."""

import pytest
import responses as rsps

ENGINE = "http://engine.test"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def plus_user(db):
    """A user with an active Plus subscription."""
    from django.contrib.auth import get_user_model

    from apps.billing.models import Plan, Subscription

    User = get_user_model()
    user = User.objects.create_user(
        email="plus@example.com",
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


@pytest.fixture
def meal_plan(db, plus_user):
    from apps.planner.models import MealPlan

    return MealPlan.objects.create(user=plus_user, week_start="2026-10-26")


@pytest.fixture
def shopping_list(db, plus_user, meal_plan):
    from apps.planner.models import ShoppingList

    return ShoppingList.objects.create(user=plus_user, plan=meal_plan, name="Week of 2026-10-26")


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------


def test_parse_iso_week_valid():
    from apps.planner.services import parse_iso_week

    d = parse_iso_week("2026-W44")
    assert d.weekday() == 0  # Monday
    assert d.isocalendar().week == 44


def test_parse_iso_week_invalid():
    from apps.planner.services import parse_iso_week

    with pytest.raises(ValueError):
        parse_iso_week("2026/44")


def test_date_to_iso_week():
    from datetime import date

    from apps.planner.services import date_to_iso_week

    d = date(2026, 10, 26)
    result = date_to_iso_week(d)
    assert result == "2026-W44"


def test_shopping_list_to_whatsapp_with_items(db, plus_user, shopping_list):
    from apps.planner.models import ShoppingItem
    from apps.planner.services import shopping_list_to_whatsapp

    ShoppingItem.objects.create(
        shopping_list=shopping_list,
        ingredient_id="i001",
        ingredient_slug="sukuma",
        display_name="Sukuma wiki",
        quantity_note="500g",
        price_estimate_kes=30,
        position=0,
    )
    ShoppingItem.objects.create(
        shopping_list=shopping_list,
        ingredient_id="i002",
        ingredient_slug="unga",
        display_name="Maize flour",
        quantity_note="2kg",
        price_estimate_kes=140,
        position=1,
    )

    text = shopping_list_to_whatsapp(shopping_list)
    assert "Sukuma wiki" in text
    assert "Maize flour" in text
    assert "~KES 30" in text
    assert "Total estimate: ~KES 170" in text


def test_shopping_list_to_whatsapp_checked_item(db, plus_user, shopping_list):
    from apps.planner.models import ShoppingItem
    from apps.planner.services import shopping_list_to_whatsapp

    ShoppingItem.objects.create(
        shopping_list=shopping_list,
        ingredient_id="i001",
        ingredient_slug="salt",
        display_name="Salt",
        checked=True,
        position=0,
    )

    text = shopping_list_to_whatsapp(shopping_list)
    assert "✓ Salt" in text


def test_shopping_list_to_whatsapp_no_items(db, plus_user, shopping_list):
    from apps.planner.services import shopping_list_to_whatsapp

    text = shopping_list_to_whatsapp(shopping_list)
    assert "Flavor Find Shopping List" in text
    assert "Total estimate" not in text


# ---------------------------------------------------------------------------
# Meal plan views
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMealPlanView:
    def test_get_plan_creates_if_missing(self, plus_client):
        response = plus_client.get("/v1/plans/2026-W44/")
        assert response.status_code == 200
        assert "entries" in response.json()

    def test_get_plan_invalid_week_format(self, plus_client):
        response = plus_client.get("/v1/plans/not-a-week/")
        assert response.status_code == 400

    def test_put_plan(self, plus_client):
        payload = {
            "entries": [
                {
                    "day": "mon",
                    "meal_type": "dinner",
                    "dish_id": "d001",
                    "dish_slug": "ugali",
                    "servings": 4,
                }
            ]
        }
        response = plus_client.put("/v1/plans/2026-W44/", payload, format="json")
        assert response.status_code == 200
        assert len(response.json()["entries"]) == 1

    def test_put_plan_replaces_entries(self, plus_client):
        """Subsequent PUT replaces all entries — not appends."""
        payload1 = {
            "entries": [
                {"day": "mon", "meal_type": "dinner", "dish_id": "d001", "dish_slug": "ugali"}
            ]
        }
        plus_client.put("/v1/plans/2026-W44/", payload1, format="json")

        payload2 = {
            "entries": [
                {"day": "tue", "meal_type": "lunch", "dish_id": "d002", "dish_slug": "chapati"}
            ]
        }
        response = plus_client.put("/v1/plans/2026-W44/", payload2, format="json")
        assert response.status_code == 200
        entries = response.json()["entries"]
        assert len(entries) == 1
        assert entries[0]["dish_slug"] == "chapati"

    def test_put_plan_invalid_week_format(self, plus_client):
        response = plus_client.put("/v1/plans/bad-week/", {"entries": []}, format="json")
        assert response.status_code == 400

    def test_meal_plan_requires_plus(self, auth_client):
        assert auth_client.get("/v1/plans/2026-W44/").status_code == 403


# ---------------------------------------------------------------------------
# Shopping list views
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestShoppingListGenerateView:
    @rsps.activate
    def test_generate_shopping_list(self, plus_client, meal_plan, plus_user):
        # Add an entry to the plan
        from apps.planner.models import MealPlanEntry

        MealPlanEntry.objects.create(
            plan=meal_plan,
            day="mon",
            meal_type="dinner",
            dish_id="d001",
            dish_slug="ugali",
            servings=4,
        )

        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(
            rsps.POST,
            f"{ENGINE}/v1/dishes/ugali/missing/",
            json={"missing": [{"id": "i001", "slug": "sukuma", "name_en": "Sukuma wiki"}]},
            status=200,
        )

        response = plus_client.post(f"/v1/plans/{meal_plan.id}/shopping-list/")
        assert response.status_code == 201
        data = response.json()
        assert "items" in data

    def test_generate_shopping_list_plan_not_found(self, plus_client):
        import uuid

        response = plus_client.post(f"/v1/plans/{uuid.uuid4()}/shopping-list/")
        assert response.status_code == 404

    def test_generate_requires_plus(self, auth_client, db):
        from django.contrib.auth import get_user_model

        from apps.planner.models import MealPlan

        User = get_user_model()
        user = User.objects.create_user(
            email="free2@example.com", password="x", status=User.Status.ACTIVE
        )
        plan = MealPlan.objects.create(user=user, week_start="2026-10-26")
        assert auth_client.post(f"/v1/plans/{plan.id}/shopping-list/").status_code == 403


@pytest.mark.django_db
class TestShoppingListDetailView:
    def test_get_shopping_list(self, plus_client, shopping_list):
        response = plus_client.get(f"/v1/shopping-lists/{shopping_list.id}/")
        assert response.status_code == 200

    def test_get_not_found(self, plus_client):
        import uuid

        assert plus_client.get(f"/v1/shopping-lists/{uuid.uuid4()}/").status_code == 404

    def test_get_requires_plus(self, auth_client, db):
        import uuid

        assert auth_client.get(f"/v1/shopping-lists/{uuid.uuid4()}/").status_code == 403


@pytest.mark.django_db
class TestShoppingItemCheckView:
    def test_check_item(self, plus_client, shopping_list):
        from apps.planner.models import ShoppingItem

        item = ShoppingItem.objects.create(
            shopping_list=shopping_list,
            ingredient_id="i001",
            ingredient_slug="sukuma",
            display_name="Sukuma wiki",
            position=0,
        )

        response = plus_client.patch(
            f"/v1/shopping-lists/{shopping_list.id}/items/{item.id}/",
            {"checked": True},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["checked"] is True

    def test_check_item_not_found(self, plus_client, shopping_list):
        import uuid

        response = plus_client.patch(
            f"/v1/shopping-lists/{shopping_list.id}/items/{uuid.uuid4()}/",
            {"checked": True},
            format="json",
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestShoppingListShareView:
    def test_share_text(self, plus_client, shopping_list):
        response = plus_client.get(f"/v1/shopping-lists/{shopping_list.id}/share/")
        assert response.status_code == 200
        assert "text" in response.json()
        assert "Flavor Find Shopping List" in response.json()["text"]

    def test_share_not_found(self, plus_client):
        import uuid

        assert plus_client.get(f"/v1/shopping-lists/{uuid.uuid4()}/share/").status_code == 404
