"""Content app tests — regions, stories."""

import pytest
import responses as rsps

ENGINE = "http://engine.test"


@pytest.fixture
def story(db):
    from apps.content.models import Story

    return Story.objects.create(
        slug="nairobi-flavours",
        title_en="Nairobi Flavours",
        title_sw="Ladha za Nairobi",
        body_en="A deep dive into Nairobi street food.",
        body_sw="Chakula cha mitaani Nairobi.",
        region_slugs="nairobi",
        author="Editorial Team",
        status=Story.Status.PUBLISHED,
    )


@pytest.fixture
def draft_story(db):
    from apps.content.models import Story

    return Story.objects.create(
        slug="mombasa-draft",
        title_en="Mombasa Draft",
        body_en="Not published yet.",
        region_slugs="mombasa",
        author="Writer",
        status=Story.Status.DRAFT,
    )


@pytest.mark.django_db
class TestRegionsView:
    @rsps.activate
    def test_regions_proxied_from_engine(self, api_client):
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/regions/",
            json={"results": [{"slug": "nairobi", "name_en": "Nairobi"}]},
            status=200,
        )
        response = api_client.get("/v1/regions/")
        assert response.status_code == 200

    @rsps.activate
    def test_regions_public_no_auth_needed(self, api_client):
        rsps.add(
            rsps.GET,
            f"{ENGINE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(rsps.GET, f"{ENGINE}/v1/regions/", json={"results": []}, status=200)
        response = api_client.get("/v1/regions/")
        assert response.status_code == 200


@pytest.mark.django_db
class TestStoryListView:
    def test_list_published_stories(self, api_client, story):
        response = api_client.get("/v1/stories/")
        assert response.status_code == 200
        slugs = [s["slug"] for s in response.json()]
        assert "nairobi-flavours" in slugs

    def test_draft_stories_excluded(self, api_client, story, draft_story):
        response = api_client.get("/v1/stories/")
        slugs = [s["slug"] for s in response.json()]
        assert "mombasa-draft" not in slugs

    def test_filter_by_region(self, api_client, story):
        response = api_client.get("/v1/stories/?region=nairobi")
        assert response.status_code == 200
        slugs = [s["slug"] for s in response.json()]
        assert "nairobi-flavours" in slugs

    def test_filter_by_nonexistent_region(self, api_client, story):
        response = api_client.get("/v1/stories/?region=kisumu")
        assert response.status_code == 200
        assert len(response.json()) == 0

    def test_stories_public_no_auth(self, api_client, story):
        response = api_client.get("/v1/stories/")
        assert response.status_code == 200


@pytest.mark.django_db
class TestStoryDetailView:
    def test_get_published_story(self, api_client, story):
        response = api_client.get(f"/v1/stories/{story.slug}/")
        assert response.status_code == 200
        assert response.json()["slug"] == story.slug
        assert "nairobi" in response.json()["region_slug_list"]

    def test_get_draft_story_returns_404(self, api_client, draft_story):
        response = api_client.get(f"/v1/stories/{draft_story.slug}/")
        assert response.status_code == 404

    def test_get_nonexistent_story_returns_404(self, api_client):
        response = api_client.get("/v1/stories/does-not-exist/")
        assert response.status_code == 404
