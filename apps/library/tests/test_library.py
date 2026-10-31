"""Library app tests — saved recipes, collections, cook log."""

import pytest
import responses as rsps

ENGINE = "http://engine.test"


@pytest.fixture
def saved_recipe(db, user):
    from apps.library.models import SavedRecipe

    return SavedRecipe.objects.create(
        user=user,
        dish_id="dish-uuid-0001",
        dish_slug="ugali",
        dataset_version="2026.10.0",
        note="",
    )


@pytest.fixture
def collection(db, user):
    from apps.library.models import Collection

    return Collection.objects.create(user=user, name="Favourites")


# ---------------------------------------------------------------------------
# Saved recipes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSavedRecipes:
    @rsps.activate
    def test_save_recipe(self, auth_client):
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        response = auth_client.post(
            "/v1/saved/",
            {"dish_id": "dish-uuid-0001", "dish_slug": "ugali"},
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["dish_slug"] == "ugali"

    @rsps.activate
    def test_list_saved_recipes(self, auth_client, saved_recipe):
        response = auth_client.get("/v1/saved/")
        assert response.status_code == 200
        assert len(response.json()) == 1

    @rsps.activate
    def test_save_same_recipe_twice_is_idempotent(self, auth_client):
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        auth_client.post("/v1/saved/", {"dish_id": "d001", "dish_slug": "ugali"}, format="json")
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        response = auth_client.post(
            "/v1/saved/", {"dish_id": "d001", "dish_slug": "ugali"}, format="json"
        )
        assert response.status_code == 200  # update, not create

    @rsps.activate
    def test_free_tier_limit_enforced(self, auth_client, user):
        """Free users cannot save more than FREE_SAVE_LIMIT recipes."""
        from apps.billing.entitlements import FREE_SAVE_LIMIT
        from apps.library.models import SavedRecipe

        # Fill up to the limit
        for i in range(FREE_SAVE_LIMIT):
            SavedRecipe.objects.create(
                user=user,
                dish_id=f"dish-{i:04d}",
                dish_slug=f"dish-{i}",
                dataset_version="2026.10.0",
            )

        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        response = auth_client.post(
            "/v1/saved/", {"dish_id": "dish-9999", "dish_slug": "new-dish"}, format="json"
        )
        assert response.status_code == 403
        assert "save_limit_reached" in response.json()["error"]["code"]

    def test_delete_saved_recipe(self, auth_client, saved_recipe):
        response = auth_client.delete(f"/v1/saved/{saved_recipe.id}/")
        assert response.status_code == 204

    def test_delete_other_users_recipe_returns_404(self, auth_client, other_user):
        from apps.library.models import SavedRecipe

        other_recipe = SavedRecipe.objects.create(
            user=other_user, dish_id="d002", dish_slug="chapati", dataset_version="2026.10.0"
        )
        assert auth_client.delete(f"/v1/saved/{other_recipe.id}/").status_code == 404

    def test_patch_saved_recipe_note(self, auth_client, saved_recipe):
        response = auth_client.patch(
            f"/v1/saved/{saved_recipe.id}/", {"note": "Make extra spicy"}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["note"] == "Make extra spicy"

    def test_patch_invalid_id_returns_404(self, auth_client):
        import uuid

        response = auth_client.patch(f"/v1/saved/{uuid.uuid4()}/", {}, format="json")
        assert response.status_code == 404

    def test_saved_recipes_require_auth(self, api_client):
        assert api_client.get("/v1/saved/").status_code == 401


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCollections:
    def test_create_collection(self, auth_client):
        response = auth_client.post("/v1/saved/collections/", {"name": "Weeknight"}, format="json")
        assert response.status_code == 201
        assert response.json()["name"] == "Weeknight"

    def test_list_collections(self, auth_client, collection):
        response = auth_client.get("/v1/saved/collections/")
        assert response.status_code == 200
        assert len(response.json()) >= 1

    def test_rename_collection(self, auth_client, collection):
        response = auth_client.patch(
            f"/v1/saved/collections/{collection.id}/", {"name": "Renamed"}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Renamed"

    def test_delete_collection(self, auth_client, collection):
        response = auth_client.delete(f"/v1/saved/collections/{collection.id}/")
        assert response.status_code == 204

    def test_delete_other_users_collection_returns_404(self, auth_client, other_user):
        from apps.library.models import Collection

        other_col = Collection.objects.create(user=other_user, name="Private")
        assert auth_client.delete(f"/v1/saved/collections/{other_col.id}/").status_code == 404

    def test_patch_other_users_collection_returns_404(self, auth_client, other_user):
        from apps.library.models import Collection

        other_col = Collection.objects.create(user=other_user, name="Private")
        assert (
            auth_client.patch(
                f"/v1/saved/collections/{other_col.id}/", {"name": "x"}, format="json"
            ).status_code
            == 404
        )

    def test_collections_require_auth(self, api_client):
        assert api_client.get("/v1/saved/collections/").status_code == 401

    @rsps.activate
    def test_save_recipe_with_collection(self, auth_client, collection):
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        response = auth_client.post(
            "/v1/saved/",
            {"dish_id": "d003", "dish_slug": "pilau", "collection_id": str(collection.id)},
            format="json",
        )
        assert response.status_code == 201

    @rsps.activate
    def test_save_recipe_invalid_collection_returns_404(self, auth_client):
        import uuid

        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        response = auth_client.post(
            "/v1/saved/",
            {"dish_id": "d004", "dish_slug": "nyama", "collection_id": str(uuid.uuid4())},
            format="json",
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Cook log
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCookLog:
    def test_log_cooked_dish(self, auth_client):
        response = auth_client.post(
            "/v1/cooked/",
            {"dish_id": "d001", "dish_slug": "ugali", "rating": 5},
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["rating"] == 5

    def test_list_cook_log(self, auth_client, user):
        from apps.library.models import CookLog

        CookLog.objects.create(user=user, dish_id="d001", dish_slug="ugali")
        response = auth_client.get("/v1/cooked/")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_cook_log_requires_auth(self, api_client):
        assert api_client.get("/v1/cooked/").status_code == 401
