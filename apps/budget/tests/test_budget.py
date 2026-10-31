"""Budget mode tests."""

import pytest
import responses as rsps

ENGINE = "http://engine.test"

SEARCH_RESPONSE = {
    "dataset_version": "2026.10.0",
    "mode": "strict",
    "results": {
        "exact": [
            {
                "dish_id": "d001",
                "slug": "ugali",
                "name_en": "Ugali",
                "tier": "exact",
                "cost_estimate_kes": 50,
            },
            {
                "dish_id": "d002",
                "slug": "pilau",
                "name_en": "Pilau",
                "tier": "exact",
                "cost_estimate_kes": 250,
            },
        ],
        "can_make": [],
        "almost": [],
    },
}


@pytest.fixture
def plus_user(db):
    from django.contrib.auth import get_user_model

    from apps.billing.models import Plan, Subscription

    User = get_user_model()
    user = User.objects.create_user(
        email="budget_plus@example.com",
        username="budgetplus",
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
class TestBudgetSuggestView:
    @rsps.activate
    def test_suggest_filters_by_budget(self, plus_client):
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(rsps.POST, f"{ENGINE}/v1/search/by-ingredients", json=SEARCH_RESPONSE, status=200)

        response = plus_client.post(
            "/v1/budget/suggest/",
            {"budget_kes": 100, "servings": 1},
            format="json",
        )
        assert response.status_code == 200
        data = response.json()
        # Only ugali (50 KES) should pass the 100 KES filter; pilau (250) should be excluded
        exact = data["results"]["exact"]
        slugs = [d["slug"] for d in exact]
        assert "ugali" in slugs
        assert "pilau" not in slugs

    @rsps.activate
    def test_suggest_includes_disclaimers(self, plus_client):
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(rsps.POST, f"{ENGINE}/v1/search/by-ingredients", json=SEARCH_RESPONSE, status=200)

        response = plus_client.post(
            "/v1/budget/suggest/",
            {"budget_kes": 500, "servings": 2},
            format="json",
        )
        assert response.status_code == 200
        data = response.json()
        assert "allergen_disclaimer" in data
        assert "cost_disclaimer" in data
        assert "budget_kes" in data

    @rsps.activate
    def test_suggest_respects_servings(self, plus_client):
        """budget_kes=200, servings=2 → budget_per_serving=100 → pilau (250) still excluded."""
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(rsps.POST, f"{ENGINE}/v1/search/by-ingredients", json=SEARCH_RESPONSE, status=200)

        response = plus_client.post(
            "/v1/budget/suggest/",
            {"budget_kes": 200, "servings": 2},
            format="json",
        )
        assert response.status_code == 200
        exact = response.json()["results"]["exact"]
        slugs = [d["slug"] for d in exact]
        assert "ugali" in slugs
        assert "pilau" not in slugs

    @rsps.activate
    def test_suggest_no_cost_estimate_included(self, plus_client):
        """Dishes without a cost estimate are always included (engine doesn't know)."""
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        no_cost_response = {
            "dataset_version": "2026.10.0",
            "mode": "strict",
            "results": {
                "exact": [
                    {
                        "dish_id": "d003",
                        "slug": "mukimo",
                        "name_en": "Mukimo",
                        "tier": "exact",
                        "cost_estimate_kes": None,
                    },
                ],
                "can_make": [],
                "almost": [],
            },
        }
        rsps.add(rsps.POST, f"{ENGINE}/v1/search/by-ingredients", json=no_cost_response, status=200)

        response = plus_client.post(
            "/v1/budget/suggest/",
            {"budget_kes": 10, "servings": 1},
            format="json",
        )
        assert response.status_code == 200
        exact = response.json()["results"]["exact"]
        assert any(d["slug"] == "mukimo" for d in exact)

    def test_suggest_requires_plus(self, auth_client):
        assert (
            auth_client.post("/v1/budget/suggest/", {"budget_kes": 100}, format="json").status_code
            == 403
        )

    @rsps.activate
    def test_suggest_missing_budget_returns_400(self, plus_client):
        response = plus_client.post("/v1/budget/suggest/", {}, format="json")
        assert response.status_code == 400
