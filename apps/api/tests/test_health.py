"""Tests for health and meta endpoints — C3, C9 build steps."""

import pytest
import responses as responses_lib


@pytest.mark.django_db
class TestHealth:
    def test_health_returns_ok(self, api_client):
        response = api_client.get("/v1/health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "service" in data
        assert "version" in data

    def test_health_no_auth_required(self, api_client):
        """Health endpoint must work without any token."""
        response = api_client.get("/v1/health/")
        assert response.status_code == 200


@pytest.mark.django_db
class TestMetaVersion:
    @responses_lib.activate
    def test_meta_version_calls_engine(self, api_client):
        """meta/version should call the engine and return dataset_version."""
        responses_lib.add(
            responses_lib.GET,
            "http://engine.test/v1/meta/version/",
            json={"engine_version": "1.0.0", "dataset_version": "2026.10.0"},
            status=200,
        )
        response = api_client.get("/v1/meta/version/")
        assert response.status_code == 200
        data = response.json()
        assert data["dataset_version"] == "2026.10.0"
        assert data["engine_version"] == "1.0.0"
        assert data["engine_status"] == "ok"

    @responses_lib.activate
    def test_meta_version_degrades_when_engine_down(self, api_client):
        """When engine is unreachable, should still return 200 with degraded status."""
        responses_lib.add(
            responses_lib.GET,
            "http://engine.test/v1/meta/version/",
            body=ConnectionError("engine down"),
        )
        response = api_client.get("/v1/meta/version/")
        assert response.status_code == 200
        data = response.json()
        assert data["engine_status"] == "degraded"

    def test_meta_version_no_auth_required(self, api_client):
        """Must work without auth."""
        # Will likely return degraded since engine.test is not real,
        # but must not 401.
        response = api_client.get("/v1/meta/version/")
        assert response.status_code == 200
