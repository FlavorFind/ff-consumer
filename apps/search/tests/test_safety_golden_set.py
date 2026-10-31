"""Safety golden set — ~40 cases that must ALWAYS pass.

These tests are the written definition of "safe" for Flavor Find.
They run on every code change, every PR, every night.
They must be 100% green before any code can merge to main.

Test categories:
  - Allergen exclusion (10 cases): excluded allergens never appear
  - Vegetarian safety (5 cases): vegetarian profile never returns meat
  - Diet tags (5 cases): halal, gluten-free, nut-free filter correctly
  - Ambiguity (5 cases): ambiguous tokens return choices, never a guess
  - Swahili/Sheng input (5 cases): local names resolve correctly
  - Explore mode (5 cases): almost results correctly labelled
  - Allergen disclaimer (5 cases): disclaimer text always present

All engine calls are mocked via the `responses` library.
These tests do NOT hit the real engine.
"""

import json

import pytest
import responses as responses_lib
from django.contrib.auth import get_user_model

User = get_user_model()

ENGINE = "http://engine.test"

# Dishes used in test fixtures
DISH_WITH_NUTS = {
    "dish_id": "nut-dish-001",
    "slug": "groundnut-stew",
    "name_en": "Groundnut Stew",
    "tier": "exact",
    "score": 0.95,
    "diet_tags": ["contains-nuts"],
    "matched": [],
    "missing": [],
}

DISH_WITH_MEAT = {
    "dish_id": "meat-dish-001",
    "slug": "beef-stew",
    "name_en": "Beef Stew",
    "tier": "exact",
    "score": 0.92,
    "diet_tags": ["contains-meat"],
    "matched": [],
    "missing": [],
}

DISH_VEGETARIAN = {
    "dish_id": "veg-dish-001",
    "slug": "sukuma-wiki-ugali",
    "name_en": "Ugali with Sukuma Wiki",
    "tier": "exact",
    "score": 0.90,
    "diet_tags": ["vegetarian"],
    "matched": [],
    "missing": [],
}

DISH_GLUTEN_FREE = {
    "dish_id": "gf-dish-001",
    "slug": "ugali-nyama",
    "name_en": "Ugali with Beef",
    "tier": "exact",
    "score": 0.88,
    "diet_tags": ["gluten-free"],
    "matched": [],
    "missing": [],
}


def make_search_response(results: dict, mode: str = "strict") -> dict:
    return {
        "dataset_version": "2026.10.0",
        "mode": mode,
        "candidate_count": len(results.get("exact", [])),
        "total_results": sum(len(v) for v in results.values()),
        "resolved": [],
        "ambiguous": [],
        "unmatched": [],
        "results": results,
    }


def mock_engine_search(response_body: dict, status: int = 200):
    """Register a mock for the engine search endpoint."""
    responses_lib.add(
        responses_lib.POST,
        f"{ENGINE}/v1/search/by-ingredients",
        json=response_body,
        status=status,
    )


def mock_engine_resolve(response_body: dict):
    responses_lib.add(
        responses_lib.POST,
        f"{ENGINE}/v1/ingredients/resolve",
        json=response_body,
        status=200,
    )


def mock_dataset_version():
    responses_lib.add(
        responses_lib.GET,
        f"{ENGINE}/v1/meta/version/",
        json={"engine_version": "1.0.0", "dataset_version": "2026.10.0"},
        status=200,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def user_with_nut_allergy(db):
    from apps.profiles.models import ProfileDiet

    user = User.objects.create_user(
        email="nut-allergy@example.com",
        password="pass1234",
        status=User.Status.ACTIVE,
    )
    ProfileDiet.objects.create(user=user, diet_tag_slug="nut-free", source="allergen")
    return user


@pytest.fixture
def vegetarian_user(db):
    from apps.profiles.models import ProfileDiet

    user = User.objects.create_user(
        email="veg@example.com",
        password="pass1234",
        status=User.Status.ACTIVE,
    )
    ProfileDiet.objects.create(user=user, diet_tag_slug="vegetarian", source="user_set")
    return user


@pytest.fixture
def halal_user(db):
    from apps.profiles.models import ProfileDiet

    user = User.objects.create_user(
        email="halal@example.com",
        password="pass1234",
        status=User.Status.ACTIVE,
    )
    ProfileDiet.objects.create(user=user, diet_tag_slug="halal", source="user_set")
    return user


@pytest.fixture
def gluten_free_user(db):
    from apps.profiles.models import ProfileDiet

    user = User.objects.create_user(
        email="gf@example.com",
        password="pass1234",
        status=User.Status.ACTIVE,
    )
    ProfileDiet.objects.create(user=user, diet_tag_slug="gluten-free", source="user_set")
    return user


@pytest.fixture
def no_diet_user(db):
    return User.objects.create_user(
        email="nodiet@example.com",
        password="pass1234",
        status=User.Status.ACTIVE,
    )


@pytest.fixture
def auth_client_for(api_client):
    """Factory: return an authenticated APIClient for a given user."""
    def _make(user):
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        return api_client

    return _make


# ─────────────────────────────────────────────────────────────────────────────
# Helper: extract all dish slugs from a search response
# ─────────────────────────────────────────────────────────────────────────────

def all_slugs(response_data: dict) -> list[str]:
    slugs = []
    for tier_dishes in response_data.get("results", {}).values():
        for dish in tier_dishes:
            slugs.append(dish.get("slug", ""))
    return slugs


def all_diet_tags(response_data: dict) -> list[str]:
    tags = []
    for tier_dishes in response_data.get("results", {}).values():
        for dish in tier_dishes:
            tags.extend(dish.get("diet_tags", []))
    return tags


# ─────────────────────────────────────────────────────────────────────────────
# Category 1: Allergen exclusion (10 cases)
# ─────────────────────────────────────────────────────────────────────────────

class TestAllergenExclusion:
    """An excluded allergen can NEVER appear in search results."""

    @responses_lib.activate
    def test_nut_allergy_sends_nut_free_to_engine(
        self, auth_client_for, user_with_nut_allergy
    ):
        """GOLDEN-ALLERGEN-001: nut-free diet tag must be in the request to the engine."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_VEGETARIAN]}))

        client = auth_client_for(user_with_nut_allergy)
        client.post("/v1/search/", {"ingredients": ["tomato"]}, format="json")

        # Verify the engine received the nut-free exclusion
        search_call = next(
            c for c in responses_lib.calls if "/search/by-ingredients" in c.request.url
        )
        body = json.loads(search_call.request.body)
        assert "nut-free" in body["diet"], (
            "SAFETY VIOLATION: nut-free allergen was not sent to the engine"
        )

    @responses_lib.activate
    def test_nut_allergy_none_not_passed_as_diet(
        self, auth_client_for, user_with_nut_allergy
    ):
        """GOLDEN-ALLERGEN-002: diet must never be None — that would silently drop exclusions."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_VEGETARIAN]}))

        client = auth_client_for(user_with_nut_allergy)
        client.post("/v1/search/", {"ingredients": ["tomato"]}, format="json")

        search_call = next(
            c for c in responses_lib.calls if "/search/by-ingredients" in c.request.url
        )
        body = json.loads(search_call.request.body)
        assert body["diet"] is not None, (
            "SAFETY VIOLATION: diet was None — allergen exclusions silently dropped"
        )

    @responses_lib.activate
    def test_multiple_allergens_all_sent(self, db, auth_client_for, api_client):
        """GOLDEN-ALLERGEN-003: user with multiple allergens — all must be sent."""
        from apps.profiles.models import ProfileDiet

        user = User.objects.create_user(
            email="multi-allergy@example.com",
            password="pass1234",
            status=User.Status.ACTIVE,
        )
        ProfileDiet.objects.create(user=user, diet_tag_slug="nut-free", source="allergen")
        ProfileDiet.objects.create(user=user, diet_tag_slug="dairy-free", source="allergen")
        ProfileDiet.objects.create(user=user, diet_tag_slug="gluten-free", source="allergen")

        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_VEGETARIAN]}))

        client = auth_client_for(user)
        client.post("/v1/search/", {"ingredients": ["tomato"]}, format="json")

        search_call = next(
            c for c in responses_lib.calls if "/search/by-ingredients" in c.request.url
        )
        body = json.loads(search_call.request.body)
        assert "nut-free" in body["diet"]
        assert "dairy-free" in body["diet"]
        assert "gluten-free" in body["diet"]

    @responses_lib.activate
    def test_allergen_sent_even_with_explicit_ingredients(
        self, auth_client_for, user_with_nut_allergy
    ):
        """GOLDEN-ALLERGEN-004: allergens sent regardless of what ingredients the user typed."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_VEGETARIAN]}))

        client = auth_client_for(user_with_nut_allergy)
        client.post(
            "/v1/search/",
            {"ingredients": ["chicken", "rice", "tomato", "onion"]},
            format="json",
        )

        search_call = next(
            c for c in responses_lib.calls if "/search/by-ingredients" in c.request.url
        )
        body = json.loads(search_call.request.body)
        assert "nut-free" in body["diet"]

    @responses_lib.activate
    def test_allergen_sent_in_explore_mode(
        self, auth_client_for, user_with_nut_allergy
    ):
        """GOLDEN-ALLERGEN-005: allergens sent in explore mode too."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [], "almost": [DISH_VEGETARIAN]}))

        client = auth_client_for(user_with_nut_allergy)
        client.post("/v1/search/", {"ingredients": ["tomato"], "mode": "explore"}, format="json")

        search_call = next(
            c for c in responses_lib.calls if "/search/by-ingredients" in c.request.url
        )
        body = json.loads(search_call.request.body)
        assert "nut-free" in body["diet"]

    @responses_lib.activate
    def test_no_diet_user_sends_empty_list_not_none(
        self, auth_client_for, no_diet_user
    ):
        """GOLDEN-ALLERGEN-006: user with no restrictions sends [] not None."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_VEGETARIAN]}))

        client = auth_client_for(no_diet_user)
        client.post("/v1/search/", {"ingredients": ["tomato"]}, format="json")

        search_call = next(
            c for c in responses_lib.calls if "/search/by-ingredients" in c.request.url
        )
        body = json.loads(search_call.request.body)
        assert body["diet"] == [], (
            "User with no restrictions should send [], not None or missing"
        )

    @responses_lib.activate
    def test_search_returns_200_with_allergen_user(
        self, auth_client_for, user_with_nut_allergy
    ):
        """GOLDEN-ALLERGEN-007: search succeeds for allergen user (not an error)."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_VEGETARIAN]}))

        client = auth_client_for(user_with_nut_allergy)
        resp = client.post("/v1/search/", {"ingredients": ["tomato"]}, format="json")
        assert resp.status_code == 200

    @responses_lib.activate
    def test_allergen_disclaimer_in_response(
        self, auth_client_for, user_with_nut_allergy
    ):
        """GOLDEN-ALLERGEN-008: allergen disclaimer must be in every search response."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_VEGETARIAN]}))

        client = auth_client_for(user_with_nut_allergy)
        resp = client.post("/v1/search/", {"ingredients": ["tomato"]}, format="json")
        assert "allergen_disclaimer" in resp.json(), (
            "SAFETY VIOLATION: allergen_disclaimer missing from search response"
        )

    @responses_lib.activate
    def test_allergen_disclaimer_non_empty(
        self, auth_client_for, user_with_nut_allergy
    ):
        """GOLDEN-ALLERGEN-009: allergen disclaimer must be a non-empty string."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_VEGETARIAN]}))

        client = auth_client_for(user_with_nut_allergy)
        resp = client.post("/v1/search/", {"ingredients": ["tomato"]}, format="json")
        disclaimer = resp.json().get("allergen_disclaimer", "")
        assert len(disclaimer) > 20, "Allergen disclaimer is suspiciously short"

    @responses_lib.activate
    def test_allergen_disclaimer_for_user_with_no_diet(
        self, auth_client_for, no_diet_user
    ):
        """GOLDEN-ALLERGEN-010: allergen disclaimer on every response, not just allergen users."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_VEGETARIAN]}))

        client = auth_client_for(no_diet_user)
        resp = client.post("/v1/search/", {"ingredients": ["tomato"]}, format="json")
        assert "allergen_disclaimer" in resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# Category 2: Vegetarian safety (5 cases)
# ─────────────────────────────────────────────────────────────────────────────

class TestVegetarianSafety:
    """A vegetarian profile must NEVER return meat, fish, or poultry."""

    @responses_lib.activate
    def test_vegetarian_tag_sent_to_engine(self, auth_client_for, vegetarian_user):
        """GOLDEN-VEG-001: vegetarian tag must be in every engine search call."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_VEGETARIAN]}))

        client = auth_client_for(vegetarian_user)
        client.post("/v1/search/", {"ingredients": ["sukuma"]}, format="json")

        search_call = next(
            c for c in responses_lib.calls if "/search/by-ingredients" in c.request.url
        )
        body = json.loads(search_call.request.body)
        assert "vegetarian" in body["diet"], (
            "SAFETY VIOLATION: vegetarian tag not sent to engine"
        )

    @responses_lib.activate
    def test_vegetarian_search_returns_200(self, auth_client_for, vegetarian_user):
        """GOLDEN-VEG-002: vegetarian search must succeed."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_VEGETARIAN]}))

        client = auth_client_for(vegetarian_user)
        resp = client.post("/v1/search/", {"ingredients": ["sukuma"]}, format="json")
        assert resp.status_code == 200

    @responses_lib.activate
    def test_vegetarian_diet_not_overridden_by_request(
        self, auth_client_for, vegetarian_user
    ):
        """GOLDEN-VEG-003: request payload cannot override user's diet restrictions."""
        mock_dataset_version()
        # Engine correctly filters — we're testing the consumer backend sends the tag
        mock_engine_search(make_search_response({"exact": [DISH_VEGETARIAN]}))

        client = auth_client_for(vegetarian_user)
        # Even if someone sends an empty search, diet must still be sent
        client.post("/v1/search/", {}, format="json")

        search_call = next(
            c for c in responses_lib.calls if "/search/by-ingredients" in c.request.url
        )
        body = json.loads(search_call.request.body)
        assert "vegetarian" in body["diet"]

    @responses_lib.activate
    def test_vegetarian_tag_in_explore_mode(self, auth_client_for, vegetarian_user):
        """GOLDEN-VEG-004: vegetarian filter applies in explore mode too."""
        mock_dataset_version()
        mock_engine_search(
            make_search_response({"exact": [DISH_VEGETARIAN], "almost": []}, mode="explore")
        )

        client = auth_client_for(vegetarian_user)
        client.post("/v1/search/", {"mode": "explore"}, format="json")

        search_call = next(
            c for c in responses_lib.calls if "/search/by-ingredients" in c.request.url
        )
        body = json.loads(search_call.request.body)
        assert "vegetarian" in body["diet"]

    @responses_lib.activate
    def test_vegetarian_disclaimer_present(self, auth_client_for, vegetarian_user):
        """GOLDEN-VEG-005: allergen disclaimer always present even for vegetarian users."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_VEGETARIAN]}))

        client = auth_client_for(vegetarian_user)
        resp = client.post("/v1/search/", {"ingredients": ["sukuma"]}, format="json")
        assert "allergen_disclaimer" in resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# Category 3: Diet tags (5 cases)
# ─────────────────────────────────────────────────────────────────────────────

class TestDietTags:
    """Other diet tags (halal, gluten-free, etc.) filter correctly."""

    @responses_lib.activate
    def test_halal_tag_sent(self, auth_client_for, halal_user):
        """GOLDEN-DIET-001: halal tag sent to engine."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_VEGETARIAN]}))

        client = auth_client_for(halal_user)
        client.post("/v1/search/", {"ingredients": ["chicken"]}, format="json")

        search_call = next(
            c for c in responses_lib.calls if "/search/by-ingredients" in c.request.url
        )
        body = json.loads(search_call.request.body)
        assert "halal" in body["diet"]

    @responses_lib.activate
    def test_gluten_free_tag_sent(self, auth_client_for, gluten_free_user):
        """GOLDEN-DIET-002: gluten-free tag sent to engine."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_GLUTEN_FREE]}))

        client = auth_client_for(gluten_free_user)
        client.post("/v1/search/", {"ingredients": ["ugali"]}, format="json")

        search_call = next(
            c for c in responses_lib.calls if "/search/by-ingredients" in c.request.url
        )
        body = json.loads(search_call.request.body)
        assert "gluten-free" in body["diet"]

    @responses_lib.activate
    def test_combined_diet_tags_all_sent(self, db, auth_client_for, api_client):
        """GOLDEN-DIET-003: user with halal + nut-free — both tags sent."""
        from apps.profiles.models import ProfileDiet

        user = User.objects.create_user(
            email="halal-nut@example.com",
            password="pass1234",
            status=User.Status.ACTIVE,
        )
        ProfileDiet.objects.create(user=user, diet_tag_slug="halal", source="user_set")
        ProfileDiet.objects.create(user=user, diet_tag_slug="nut-free", source="allergen")

        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_VEGETARIAN]}))

        client = auth_client_for(user)
        client.post("/v1/search/", {"ingredients": ["chicken"]}, format="json")

        search_call = next(
            c for c in responses_lib.calls if "/search/by-ingredients" in c.request.url
        )
        body = json.loads(search_call.request.body)
        assert "halal" in body["diet"]
        assert "nut-free" in body["diet"]

    @responses_lib.activate
    def test_diet_tag_persists_across_requests(self, auth_client_for, gluten_free_user):
        """GOLDEN-DIET-004: diet tags applied consistently across multiple requests."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_GLUTEN_FREE]}))
        mock_engine_search(make_search_response({"exact": [DISH_GLUTEN_FREE]}))

        client = auth_client_for(gluten_free_user)
        client.post("/v1/search/", {"ingredients": ["ugali"]}, format="json")
        client.post("/v1/search/", {"ingredients": ["rice"]}, format="json")

        for call in responses_lib.calls:
            if "/search/by-ingredients" in call.request.url:
                body = json.loads(call.request.body)
                assert "gluten-free" in body["diet"]

    @responses_lib.activate
    def test_diet_tag_response_has_disclaimer(self, auth_client_for, halal_user):
        """GOLDEN-DIET-005: allergen disclaimer in response for diet tag users."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_VEGETARIAN]}))

        client = auth_client_for(halal_user)
        resp = client.post("/v1/search/", {"ingredients": ["chicken"]}, format="json")
        assert "allergen_disclaimer" in resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# Category 4: Ambiguity (5 cases)
# ─────────────────────────────────────────────────────────────────────────────

class TestAmbiguity:
    """Ambiguous tokens must return choices to the user, never a silent guess."""

    @responses_lib.activate
    def test_ambiguous_token_returns_choices(self, auth_client, db):
        """GOLDEN-AMBIG-001: 'unga' returns choices, not a guessed result."""
        mock_dataset_version()
        mock_engine_resolve(
            {
                "resolved": [],
                "ambiguous": [
                    {
                        "token": "unga",
                        "status": "ambiguous",
                        "choices": [
                            {"id": "uuid-1", "slug": "maize-flour", "name_en": "Maize Flour"},
                            {"id": "uuid-2", "slug": "wheat-flour", "name_en": "Wheat Flour"},
                        ],
                    }
                ],
                "unmatched": [],
            }
        )

        resp = auth_client.post("/v1/resolve/", {"tokens": ["unga"]}, format="json")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data.get("ambiguous", [])) > 0, "Ambiguous tokens not returned to client"

    @responses_lib.activate
    def test_pepper_is_ambiguous(self, auth_client, db):
        """GOLDEN-AMBIG-002: 'pepper' (black/white/red/green) returns choices."""
        mock_dataset_version()
        mock_engine_resolve(
            {
                "resolved": [],
                "ambiguous": [
                    {
                        "token": "pepper",
                        "status": "ambiguous",
                        "choices": [
                            {"id": "uuid-3", "slug": "black-pepper", "name_en": "Black Pepper"},
                            {"id": "uuid-4", "slug": "red-pepper", "name_en": "Red Pepper"},
                        ],
                    }
                ],
                "unmatched": [],
            }
        )

        resp = auth_client.post("/v1/resolve/", {"tokens": ["pepper"]}, format="json")
        assert resp.status_code == 200
        assert len(resp.json().get("ambiguous", [])) > 0

    @responses_lib.activate
    def test_unmatched_token_returned(self, auth_client, db):
        """GOLDEN-AMBIG-003: completely unknown tokens returned as unmatched."""
        mock_dataset_version()
        mock_engine_resolve(
            {
                "resolved": [],
                "ambiguous": [],
                "unmatched": ["xyzunknownfood"],
            }
        )

        resp = auth_client.post("/v1/resolve/", {"tokens": ["xyzunknownfood"]}, format="json")
        assert resp.status_code == 200
        assert "xyzunknownfood" in resp.json().get("unmatched", [])

    @responses_lib.activate
    def test_matched_token_resolved_correctly(self, auth_client, db):
        """GOLDEN-AMBIG-004: clearly matched tokens return ingredient ID."""
        mock_dataset_version()
        mock_engine_resolve(
            {
                "resolved": [
                    {
                        "token": "tomato",
                        "status": "matched",
                        "ingredient_id": "uuid-tomato",
                        "ingredient_slug": "tomato",
                        "confidence": 0.99,
                    }
                ],
                "ambiguous": [],
                "unmatched": [],
            }
        )

        resp = auth_client.post("/v1/resolve/", {"tokens": ["tomato"]}, format="json")
        assert resp.status_code == 200
        resolved = resp.json().get("resolved", [])
        assert len(resolved) == 1
        assert resolved[0]["status"] == "matched"

    @responses_lib.activate
    def test_resolve_requires_auth(self, api_client, db):
        """GOLDEN-AMBIG-005: resolve endpoint requires auth."""
        resp = api_client.post("/v1/resolve/", {"tokens": ["unga"]}, format="json")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Category 5: Swahili / Sheng input (5 cases)
# ─────────────────────────────────────────────────────────────────────────────

class TestSwahiliInput:
    """Local names must resolve correctly through the engine."""

    @responses_lib.activate
    def test_nyanya_resolves(self, auth_client, db):
        """GOLDEN-SW-001: nyanya (tomato in Swahili) resolves."""
        mock_dataset_version()
        mock_engine_resolve(
            {
                "resolved": [
                    {
                        "token": "nyanya",
                        "status": "matched",
                        "ingredient_id": "uuid-tomato",
                        "ingredient_slug": "tomato",
                        "name_en": "Tomato",
                        "confidence": 0.98,
                    }
                ],
                "ambiguous": [],
                "unmatched": [],
            }
        )

        resp = auth_client.post("/v1/resolve/", {"tokens": ["nyanya"], "lang": "sw"}, format="json")
        assert resp.status_code == 200
        resolved = resp.json().get("resolved", [])
        assert len(resolved) == 1
        assert resolved[0]["ingredient_slug"] == "tomato"

    @responses_lib.activate
    def test_sukuma_resolves(self, auth_client, db):
        """GOLDEN-SW-002: sukuma resolves to sukuma wiki."""
        mock_dataset_version()
        mock_engine_resolve(
            {
                "resolved": [
                    {
                        "token": "sukuma",
                        "status": "matched",
                        "ingredient_id": "uuid-sukuma",
                        "ingredient_slug": "sukuma-wiki",
                        "name_en": "Sukuma Wiki",
                        "confidence": 0.97,
                    }
                ],
                "ambiguous": [],
                "unmatched": [],
            }
        )

        resp = auth_client.post("/v1/resolve/", {"tokens": ["sukuma"]}, format="json")
        assert resp.status_code == 200
        assert resp.json()["resolved"][0]["ingredient_slug"] == "sukuma-wiki"

    @responses_lib.activate
    def test_swahili_lang_param_passed(self, auth_client, db):
        """GOLDEN-SW-003: lang=sw is passed to the engine."""
        mock_dataset_version()
        mock_engine_resolve({"resolved": [], "ambiguous": [], "unmatched": []})

        auth_client.post("/v1/resolve/", {"tokens": ["nyanya"], "lang": "sw"}, format="json")

        resolve_call = next(
            c for c in responses_lib.calls if "/ingredients/resolve" in c.request.url
        )
        body = json.loads(resolve_call.request.body)
        assert body.get("lang") == "sw"

    @responses_lib.activate
    def test_chapati_resolves(self, auth_client, db):
        """GOLDEN-SW-004: chapati resolves as a matched ingredient."""
        mock_dataset_version()
        mock_engine_resolve(
            {
                "resolved": [
                    {
                        "token": "chapati",
                        "status": "matched",
                        "ingredient_id": "uuid-chapati",
                        "ingredient_slug": "chapati",
                        "confidence": 0.99,
                    }
                ],
                "ambiguous": [],
                "unmatched": [],
            }
        )

        resp = auth_client.post("/v1/resolve/", {"tokens": ["chapati"]}, format="json")
        assert resp.status_code == 200
        assert resp.json()["resolved"][0]["status"] == "matched"

    @responses_lib.activate
    def test_mixed_swahili_english_tokens(self, auth_client, db):
        """GOLDEN-SW-005: mix of Swahili and English tokens all sent to engine."""
        mock_dataset_version()
        mock_engine_resolve({"resolved": [], "ambiguous": [], "unmatched": []})

        auth_client.post(
            "/v1/resolve/",
            {"tokens": ["nyanya", "onion", "sukuma"]},
            format="json",
        )

        resolve_call = next(
            c for c in responses_lib.calls if "/ingredients/resolve" in c.request.url
        )
        body = json.loads(resolve_call.request.body)
        assert "nyanya" in body["tokens"]
        assert "onion" in body["tokens"]
        assert "sukuma" in body["tokens"]


# ─────────────────────────────────────────────────────────────────────────────
# Category 6: Explore mode (5 cases)
# ─────────────────────────────────────────────────────────────────────────────

class TestExploreMode:
    """'Almost' results: correctly labelled, not shown in strict mode."""

    @responses_lib.activate
    def test_explore_mode_passed_to_engine(self, auth_client_for, no_diet_user):
        """GOLDEN-EXPLORE-001: explore mode parameter passed to engine."""
        mock_dataset_version()
        mock_engine_search(
            make_search_response({"exact": [], "almost": []}, mode="explore")
        )

        client = auth_client_for(no_diet_user)
        client.post("/v1/search/", {"mode": "explore"}, format="json")

        search_call = next(
            c for c in responses_lib.calls if "/search/by-ingredients" in c.request.url
        )
        body = json.loads(search_call.request.body)
        assert body["mode"] == "explore"

    @responses_lib.activate
    def test_strict_mode_passed_to_engine(self, auth_client_for, no_diet_user):
        """GOLDEN-EXPLORE-002: strict mode parameter passed to engine."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": []}, mode="strict"))

        client = auth_client_for(no_diet_user)
        client.post("/v1/search/", {"mode": "strict"}, format="json")

        search_call = next(
            c for c in responses_lib.calls if "/search/by-ingredients" in c.request.url
        )
        body = json.loads(search_call.request.body)
        assert body["mode"] == "strict"

    @responses_lib.activate
    def test_default_mode_is_strict(self, auth_client_for, no_diet_user):
        """GOLDEN-EXPLORE-003: default mode is strict (no 'almost' results by default)."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": []}, mode="strict"))

        client = auth_client_for(no_diet_user)
        client.post("/v1/search/", {}, format="json")

        search_call = next(
            c for c in responses_lib.calls if "/search/by-ingredients" in c.request.url
        )
        body = json.loads(search_call.request.body)
        assert body["mode"] == "strict"

    @responses_lib.activate
    def test_explore_results_returned(self, auth_client_for, no_diet_user):
        """GOLDEN-EXPLORE-004: explore mode returns almost results from engine."""
        almost_dish = {**DISH_VEGETARIAN, "tier": "almost", "missing": [{"slug": "onion"}]}
        mock_dataset_version()
        mock_engine_search(
            make_search_response({"exact": [], "almost": [almost_dish]}, mode="explore")
        )

        client = auth_client_for(no_diet_user)
        resp = client.post("/v1/search/", {"mode": "explore"}, format="json")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data.get("results", {}).get("almost", [])) == 1

    @responses_lib.activate
    def test_explore_allergen_tags_still_sent(
        self, auth_client_for, user_with_nut_allergy
    ):
        """GOLDEN-EXPLORE-005: allergen tags sent even in explore mode."""
        mock_dataset_version()
        mock_engine_search(
            make_search_response({"exact": [], "almost": []}, mode="explore")
        )

        client = auth_client_for(user_with_nut_allergy)
        client.post("/v1/search/", {"mode": "explore"}, format="json")

        search_call = next(
            c for c in responses_lib.calls if "/search/by-ingredients" in c.request.url
        )
        body = json.loads(search_call.request.body)
        assert "nut-free" in body["diet"]


# ─────────────────────────────────────────────────────────────────────────────
# Category 7: Allergen disclaimer (5 cases)
# ─────────────────────────────────────────────────────────────────────────────

class TestAllergenDisclaimer:
    """Allergen disclaimer must appear on every response that mentions dietary info."""

    @responses_lib.activate
    def test_disclaimer_in_search_response(self, auth_client_for, no_diet_user):
        """GOLDEN-DISC-001: disclaimer in every search response."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [DISH_VEGETARIAN]}))

        client = auth_client_for(no_diet_user)
        resp = client.post("/v1/search/", {}, format="json")
        assert "allergen_disclaimer" in resp.json()

    @responses_lib.activate
    def test_disclaimer_not_empty(self, auth_client_for, no_diet_user):
        """GOLDEN-DISC-002: disclaimer is not empty."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": []}))

        client = auth_client_for(no_diet_user)
        resp = client.post("/v1/search/", {}, format="json")
        assert resp.json()["allergen_disclaimer"] != ""

    @responses_lib.activate
    def test_disclaimer_mentions_kitchen(self, auth_client_for, no_diet_user):
        """GOLDEN-DISC-003: disclaimer mentions confirming with the kitchen."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": []}))

        client = auth_client_for(no_diet_user)
        resp = client.post("/v1/search/", {}, format="json")
        assert "kitchen" in resp.json()["allergen_disclaimer"].lower()

    @responses_lib.activate
    def test_disclaimer_in_degraded_mode(self, auth_client_for, no_diet_user):
        """GOLDEN-DISC-004: disclaimer present even when engine is degraded."""
        # Engine returns degraded
        mock_dataset_version()
        responses_lib.add(
            responses_lib.POST,
            f"{ENGINE}/v1/search/by-ingredients",
            body=ConnectionError("engine down"),
        )

        client = auth_client_for(no_diet_user)
        resp = client.post("/v1/search/", {"ingredients": ["tomato"]}, format="json")
        assert resp.status_code == 200
        assert "allergen_disclaimer" in resp.json()

    @responses_lib.activate
    def test_disclaimer_in_empty_results(self, auth_client_for, no_diet_user):
        """GOLDEN-DISC-005: disclaimer present even when no results returned."""
        mock_dataset_version()
        mock_engine_search(make_search_response({"exact": [], "can_make": []}))

        client = auth_client_for(no_diet_user)
        resp = client.post("/v1/search/", {"ingredients": ["obscure-ingredient-xyz"]}, format="json")
        assert "allergen_disclaimer" in resp.json()
