"""Tests for the pantry app — C13 build step, permission tests."""

import pytest

INGREDIENT = {
    "ingredient_id": "a3f9b1c2-0000-0000-0000-000000000001",
    "ingredient_slug": "sukuma-wiki",
    "display_name": "Sukuma Wiki",
}


@pytest.mark.django_db
class TestPantryCRUD:
    def test_list_empty_pantry(self, auth_client):
        response = auth_client.get("/v1/pantry/")
        assert response.status_code == 200
        assert response.json() == []

    def test_add_item(self, auth_client):
        response = auth_client.post("/v1/pantry/", INGREDIENT, format="json")
        assert response.status_code == 201
        data = response.json()
        assert data["ingredient_slug"] == "sukuma-wiki"
        assert data["display_name"] == "Sukuma Wiki"

    def test_add_duplicate_updates(self, auth_client):
        auth_client.post("/v1/pantry/", INGREDIENT, format="json")
        updated = {**INGREDIENT, "display_name": "Sukuma Wiki (Updated)"}
        response = auth_client.post("/v1/pantry/", updated, format="json")
        assert response.status_code == 200
        assert response.json()["display_name"] == "Sukuma Wiki (Updated)"

    def test_list_shows_added_item(self, auth_client):
        auth_client.post("/v1/pantry/", INGREDIENT, format="json")
        response = auth_client.get("/v1/pantry/")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_delete_item(self, auth_client):
        resp = auth_client.post("/v1/pantry/", INGREDIENT, format="json")
        item_id = resp.json()["id"]
        delete_resp = auth_client.delete(f"/v1/pantry/{item_id}/")
        assert delete_resp.status_code == 204
        list_resp = auth_client.get("/v1/pantry/")
        assert len(list_resp.json()) == 0

    def test_delete_nonexistent_returns_404(self, auth_client):
        response = auth_client.delete("/v1/pantry/00000000-0000-0000-0000-000000000000/")
        assert response.status_code == 404

    def test_invalid_ingredient_id(self, auth_client):
        bad = {**INGREDIENT, "ingredient_id": "not-a-uuid"}
        response = auth_client.post("/v1/pantry/", bad, format="json")
        assert response.status_code == 400

    def test_pantry_requires_auth(self, api_client):
        response = api_client.get("/v1/pantry/")
        assert response.status_code == 401


@pytest.mark.django_db
class TestPantryPermissions:
    """User A cannot access User B's pantry."""

    def test_user_cannot_delete_other_users_item(self, auth_client, other_user):
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken

        # Add item as other_user
        other_client = APIClient()
        refresh = RefreshToken.for_user(other_user)
        other_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        resp = other_client.post("/v1/pantry/", INGREDIENT, format="json")
        item_id = resp.json()["id"]

        # Try to delete as auth_client (different user)
        response = auth_client.delete(f"/v1/pantry/{item_id}/")
        assert response.status_code == 404  # Not 204, not 403

    def test_user_cannot_see_other_users_pantry(self, auth_client, other_user):
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken

        # Add item as other_user
        other_client = APIClient()
        refresh = RefreshToken.for_user(other_user)
        other_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        other_client.post("/v1/pantry/", INGREDIENT, format="json")

        # List as auth_client — must see empty list
        response = auth_client.get("/v1/pantry/")
        assert response.status_code == 200
        assert response.json() == []
