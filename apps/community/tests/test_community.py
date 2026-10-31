"""Community app tests — submissions and reviews."""

import pytest
import responses as rsps

ENGINE = "http://engine.test"


@pytest.mark.django_db
class TestSubmissions:
    def test_create_submission(self, auth_client):
        response = auth_client.post(
            "/v1/submissions/",
            {
                "name_en": "Grandma's Ugali",
                "description": "A classic recipe",
                "ingredients": ["maize flour", "water", "salt"],
                "steps": ["Boil water", "Add flour", "Stir"],
            },
            format="json",
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "draft"

    def test_list_own_submissions(self, auth_client, user):
        from apps.community.models import Submission

        Submission.objects.create(
            user=user, payload={"name_en": "Test"}, status=Submission.Status.DRAFT
        )
        response = auth_client.get("/v1/submissions/")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_get_submission_detail(self, auth_client, user):
        from apps.community.models import Submission

        sub = Submission.objects.create(
            user=user, payload={"name_en": "Test"}, status=Submission.Status.DRAFT
        )
        response = auth_client.get(f"/v1/submissions/{sub.id}/")
        assert response.status_code == 200
        assert response.json()["id"] == str(sub.id)

    def test_get_other_users_submission_returns_404(self, auth_client, other_user):
        from apps.community.models import Submission

        other_sub = Submission.objects.create(
            user=other_user, payload={"name_en": "Theirs"}, status=Submission.Status.DRAFT
        )
        assert auth_client.get(f"/v1/submissions/{other_sub.id}/").status_code == 404

    def test_submission_missing_required_field(self, auth_client):
        response = auth_client.post(
            "/v1/submissions/",
            {"name_en": "Incomplete"},  # missing description, ingredients, steps
            format="json",
        )
        assert response.status_code == 400

    def test_submissions_require_auth(self, api_client):
        assert api_client.get("/v1/submissions/").status_code == 401


@pytest.mark.django_db
class TestReviews:
    @rsps.activate
    def test_create_review(self, auth_client):
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/dishes/ugali/",
            json={"id": "dish-uuid-ugali", "slug": "ugali"},
            status=200,
        )
        response = auth_client.post(
            "/v1/dishes/ugali/reviews/",
            {"stars": 5, "text": "Delicious!"},
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["stars"] == 5
        assert response.json()["status"] == "pending"

    @rsps.activate
    def test_update_existing_review(self, auth_client):
        """Posting a second review for the same dish updates the first."""
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/dishes/ugali/",
            json={"id": "dish-uuid-ugali", "slug": "ugali"},
            status=200,
        )
        auth_client.post("/v1/dishes/ugali/reviews/", {"stars": 3}, format="json")

        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/dishes/ugali/",
            json={"id": "dish-uuid-ugali", "slug": "ugali"},
            status=200,
        )
        response = auth_client.post(
            "/v1/dishes/ugali/reviews/", {"stars": 5, "text": "Changed mind!"}, format="json"
        )
        assert response.status_code == 200  # update, not create
        assert response.json()["stars"] == 5

    @rsps.activate
    def test_list_approved_reviews(self, auth_client, user):
        from apps.community.models import Review

        Review.objects.create(
            user=user,
            dish_id="dish-uuid-ugali",
            dish_slug="ugali",
            stars=4,
            status=Review.Status.APPROVED,
        )
        Review.objects.create(
            user=user,
            dish_id="dish-uuid-ugali2",
            dish_slug="ugali",
            stars=2,
            status=Review.Status.PENDING,
        )
        response = auth_client.get("/v1/dishes/ugali/reviews/")
        assert response.status_code == 200
        # Only approved reviews
        assert len(response.json()) == 1

    @rsps.activate
    def test_review_invalid_stars(self, auth_client):
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/dishes/ugali/",
            json={"id": "dish-uuid-ugali", "slug": "ugali"},
            status=200,
        )
        response = auth_client.post("/v1/dishes/ugali/reviews/", {"stars": 10}, format="json")
        assert response.status_code == 400

    def test_reviews_require_auth(self, api_client):
        assert api_client.post("/v1/dishes/ugali/reviews/", {}).status_code == 401
