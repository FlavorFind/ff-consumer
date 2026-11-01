"""Search services tests — personalisation, region boost, dish detail."""

import pytest
import responses as rsps

ENGINE = "http://engine.test"


@pytest.mark.django_db
class TestSearchService:
    @rsps.activate
    def test_search_injects_diet_tags(self, user):
        from apps.profiles.models import ProfileDiet
        from apps.search.services import search

        ProfileDiet.objects.create(user=user, diet_tag_slug="vegetarian")

        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(
            rsps.POST,
            f"{ENGINE}/v1/search/by-ingredients",
            json={
                "results": {"exact": [], "can_make": [], "almost": []},
                "dataset_version": "2026.10.0",
            },
            status=200,
        )

        result = search(user=user, ingredients=["tomato"])
        assert "allergen_disclaimer" in result

        # Verify vegetarian was sent to engine
        import json

        body = json.loads(rsps.calls[-1].request.body)
        assert "vegetarian" in body["diet"]

    @rsps.activate
    def test_search_injects_pantry(self, user):
        from apps.pantry.models import PantryItem
        from apps.search.services import search

        PantryItem.objects.create(
            user=user,
            ingredient_id="ing-001",
            ingredient_slug="onion",
            display_name="Onion",
        )

        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(
            rsps.POST,
            f"{ENGINE}/v1/search/by-ingredients",
            json={"results": {}, "dataset_version": "2026.10.0"},
            status=200,
        )

        search(user=user, ingredients=["tomato"])

        import json

        body = json.loads(rsps.calls[-1].request.body)
        assert "onion" in body["ingredients"]
        assert "tomato" in body["ingredients"]

    @rsps.activate
    def test_search_region_boost(self, user):
        from apps.profiles.models import Profile
        from apps.search.services import search

        Profile.objects.create(user=user, region_slug="nairobi")

        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(
            rsps.POST,
            f"{ENGINE}/v1/search/by-ingredients",
            json={
                "results": {
                    "exact": [
                        {"slug": "nyama-choma", "region_slug": "mombasa"},
                        {"slug": "nyama-local", "region_slug": "nairobi"},
                    ],
                    "can_make": [],
                    "almost": [],
                },
                "dataset_version": "2026.10.0",
            },
            status=200,
        )

        result = search(user=user, ingredients=["meat"])
        exact = result["results"]["exact"]
        assert exact[0]["region_slug"] == "nairobi"

    @rsps.activate
    def test_search_no_region_boost_skipped(self, user):
        """Region boost is skipped when user has no profile."""
        from apps.search.services import search

        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(
            rsps.POST,
            f"{ENGINE}/v1/search/by-ingredients",
            json={
                "results": {"exact": [], "can_make": [], "almost": []},
                "dataset_version": "2026.10.0",
            },
            status=200,
        )

        # Should not raise even with no profile
        result = search(user=user, ingredients=["rice"], boost_region=True)
        assert "allergen_disclaimer" in result


@pytest.mark.django_db
class TestGetDishService:
    @rsps.activate
    def test_get_dish_attaches_disclaimer_when_diet_tags(self):
        from apps.search.services import get_dish

        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/dishes/ugali/",
            json={"slug": "ugali", "diet_tags": ["vegetarian"]},
            status=200,
        )

        result = get_dish("ugali")
        assert "allergen_disclaimer" in result

    @rsps.activate
    def test_get_dish_no_disclaimer_without_diet_tags(self):
        from apps.search.services import get_dish

        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(rsps.GET, f"{ENGINE}/v1/dishes/plain/", json={"slug": "plain"}, status=200)

        result = get_dish("plain")
        assert "allergen_disclaimer" not in result


@pytest.mark.django_db
class TestResolveService:
    @rsps.activate
    def test_resolve_delegates_to_engine(self):
        from apps.search.services import resolve

        rsps.add(
            rsps.POST,
            f"{ENGINE}/v1/ingredients/resolve",
            json={"results": [{"token": "unga", "status": "matched"}]},
            status=200,
        )

        result = resolve(["unga"])
        assert result["results"][0]["token"] == "unga"


@pytest.mark.django_db
class TestGetIngredientsService:
    @rsps.activate
    def test_get_ingredients_delegates_to_engine(self):
        from apps.search.services import get_ingredients

        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/ingredients/",
            json={"results": [{"slug": "tomato"}]},
            status=200,
        )

        result = get_ingredients("tom")
        assert len(result["results"]) == 1
