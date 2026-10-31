"""Profile and diet tag view tests."""

import pytest


@pytest.mark.django_db
class TestProfileView:
    def test_get_creates_profile_if_missing(self, auth_client):
        response = auth_client.get("/v1/me/profile/")
        assert response.status_code == 200
        assert "household_size" in response.json()

    def test_patch_profile(self, auth_client):
        response = auth_client.patch(
            "/v1/me/profile/",
            {"household_size": 3, "region_slug": "nairobi"},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["household_size"] == 3
        assert response.json()["region_slug"] == "nairobi"

    def test_patch_budget(self, auth_client):
        response = auth_client.patch(
            "/v1/me/profile/",
            {"budget_kes_per_meal": 150},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["budget_kes_per_meal"] == "150.00"

    def test_profile_requires_auth(self, api_client):
        assert api_client.get("/v1/me/profile/").status_code == 401


@pytest.mark.django_db
class TestProfileDietView:
    def test_get_diet_tags_empty(self, auth_client):
        response = auth_client.get("/v1/me/diet/")
        assert response.status_code == 200
        assert response.json() == []

    def test_patch_sets_diet_tags(self, auth_client):
        response = auth_client.patch(
            "/v1/me/diet/",
            {"diet_tags": ["vegetarian", "gluten-free"]},
            format="json",
        )
        assert response.status_code == 200
        slugs = [t["diet_tag_slug"] for t in response.json()]
        assert "vegetarian" in slugs
        assert "gluten-free" in slugs

    def test_patch_replaces_tags(self, auth_client):
        auth_client.patch("/v1/me/diet/", {"diet_tags": ["vegetarian"]}, format="json")
        auth_client.patch("/v1/me/diet/", {"diet_tags": ["halal"]}, format="json")
        response = auth_client.get("/v1/me/diet/")
        slugs = [t["diet_tag_slug"] for t in response.json()]
        assert slugs == ["halal"]
        assert "vegetarian" not in slugs

    def test_patch_empty_clears_tags(self, auth_client):
        auth_client.patch("/v1/me/diet/", {"diet_tags": ["vegetarian"]}, format="json")
        auth_client.patch("/v1/me/diet/", {"diet_tags": []}, format="json")
        response = auth_client.get("/v1/me/diet/")
        assert response.json() == []

    def test_diet_requires_auth(self, api_client):
        assert api_client.get("/v1/me/diet/").status_code == 401
