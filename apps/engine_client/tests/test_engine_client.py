"""Engine client tests — circuit breaker, caching, search safety, all endpoints.

Uses `responses` library to mock HTTP calls without a live engine.
Targets 95%+ coverage for apps/engine_client.
"""

import pytest
import responses as rsps
from django.core.cache import cache

BASE = "http://engine.test"


@pytest.fixture
def client():
    """Fresh EngineClient with test settings."""
    from apps.engine_client.client import EngineClient

    # Clear circuit breaker and dataset version cache before each test
    cache.clear()
    return EngineClient(
        base_url=BASE,
        api_key="ffk_test_pub0000000000000000000000000000000000000000",
        internal_key="ffk_test_int0000000000000000000000000000000000000000",
        timeout=5.0,
    )


# ---------------------------------------------------------------------------
# Dataset version
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDatasetVersion:
    @rsps.activate
    def test_get_dataset_version_fetches_and_caches(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/meta/version/",
            json={"engine_version": "1.0.0", "dataset_version": "2026.10.0"},
            status=200,
        )
        version = client.get_dataset_version()
        assert version == "2026.10.0"
        # Second call should use cache (only one HTTP request)
        version2 = client.get_dataset_version()
        assert version2 == "2026.10.0"
        assert len(rsps.calls) == 1

    @rsps.activate
    def test_get_dataset_version_engine_down_returns_cached(self, client):
        from django.core.cache import cache as django_cache

        django_cache.set("ffconsumer:engine:dataset_version", "2026.10.0", timeout=3600)
        rsps.add(rsps.GET, f"{BASE}/v1/meta/version/", body=ConnectionError("down"))
        version = client.get_dataset_version()
        assert version == "2026.10.0"

    @rsps.activate
    def test_get_dataset_version_engine_down_no_cache_returns_unknown(self, client):
        rsps.add(rsps.GET, f"{BASE}/v1/meta/version/", body=ConnectionError("down"))
        # Force circuit open after first failure by calling _record_failure multiple times
        for _ in range(5):
            client._record_failure()
        version = client.get_dataset_version()
        assert version == "unknown"

    @rsps.activate
    def test_refresh_dataset_version(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/meta/version/",
            json={"dataset_version": "2026.11.0"},
            status=200,
        )
        version = client.refresh_dataset_version()
        assert version == "2026.11.0"


# ---------------------------------------------------------------------------
# Health / meta
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestHealthMeta:
    @rsps.activate
    def test_health_ping(self, client):
        # Provide version endpoint too (get_dataset_version called in some paths)
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/health/",
            json={"status": "ok"},
            status=200,
        )
        result = client.health_ping()
        assert result["status"] == "ok"

    @rsps.activate
    def test_get_version(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/meta/version/",
            json={"engine_version": "1.0.0", "dataset_version": "2026.10.0"},
            status=200,
        )
        result = client.get_version()
        assert result["engine_version"] == "1.0.0"


# ---------------------------------------------------------------------------
# Search — SAFETY CRITICAL
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSearch:
    @rsps.activate
    def test_search_success(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(
            rsps.POST,
            f"{BASE}/v1/search/by-ingredients",
            json={
                "dataset_version": "2026.10.0",
                "mode": "strict",
                "results": {"exact": [], "can_make": [], "almost": []},
            },
            status=200,
        )
        result = client.search(
            ingredients=["tomato", "onion"],
            diet=["vegetarian"],
            mode="strict",
        )
        assert "results" in result
        assert result["dataset_version"] == "2026.10.0"

    def test_search_diet_none_raises(self, client):
        """Safety rule: diet=None must raise, not silently drop allergen exclusions."""
        with pytest.raises(ValueError, match="diet must be provided"):
            client.search(ingredients=["tomato"], diet=None)

    @rsps.activate
    def test_search_uses_cache(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(
            rsps.POST,
            f"{BASE}/v1/search/by-ingredients",
            json={"results": {}, "dataset_version": "2026.10.0"},
            status=200,
        )
        # First call
        client.search(ingredients=["tomato"], diet=[])
        # Second call — should hit cache, not make another POST
        client.search(ingredients=["tomato"], diet=[])
        post_calls = [c for c in rsps.calls if c.request.method == "POST"]
        assert len(post_calls) == 1

    @rsps.activate
    def test_search_engine_down_returns_degraded(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(
            rsps.POST,
            f"{BASE}/v1/search/by-ingredients",
            body=ConnectionError("engine down"),
        )
        result = client.search(ingredients=["tomato"], diet=[])
        assert result["engine_status"] == "degraded"

    @rsps.activate
    def test_search_circuit_open_returns_degraded(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        # Open the circuit manually
        for _ in range(5):
            client._record_failure()
        result = client.search(ingredients=["tomato"], diet=[])
        assert result["engine_status"] == "degraded"

    @rsps.activate
    def test_search_with_exclude_and_meal_type(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(
            rsps.POST,
            f"{BASE}/v1/search/by-ingredients",
            json={"results": {}, "dataset_version": "2026.10.0"},
            status=200,
        )
        result = client.search(
            ingredients=["rice"],
            diet=[],
            exclude=["beef"],
            meal_type="lunch",
        )
        assert "results" in result
        # Verify request body
        import json

        sent_body = json.loads(rsps.calls[-1].request.body)
        assert sent_body["exclude"] == ["beef"]
        assert sent_body["meal_type"] == "lunch"


# ---------------------------------------------------------------------------
# Resolve / Ingredients
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestResolveIngredients:
    @rsps.activate
    def test_resolve_success(self, client):
        rsps.add(
            rsps.POST,
            f"{BASE}/v1/ingredients/resolve",
            json={"results": [{"token": "unga", "status": "matched"}]},
            status=200,
        )
        result = client.resolve(["unga"])
        assert result["results"][0]["token"] == "unga"

    @rsps.activate
    def test_get_ingredients_autocomplete(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/ingredients/",
            json={"results": [{"slug": "tomato", "name_en": "Tomato"}]},
            status=200,
        )
        result = client.get_ingredients("tom")
        assert len(result["results"]) == 1

    @rsps.activate
    def test_get_ingredients_uses_cache(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/ingredients/",
            json={"results": []},
            status=200,
        )
        client.get_ingredients("tom")
        client.get_ingredients("tom")
        assert len(rsps.calls) == 1


# ---------------------------------------------------------------------------
# Dishes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDishes:
    @rsps.activate
    def test_get_dish(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/dishes/ugali/",
            json={"slug": "ugali", "name_en": "Ugali"},
            status=200,
        )
        result = client.get_dish("ugali")
        assert result["slug"] == "ugali"

    @rsps.activate
    def test_get_dish_uses_cache(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/dishes/ugali/",
            json={"slug": "ugali"},
            status=200,
        )
        client.get_dish("ugali")
        client.get_dish("ugali")
        dish_calls = [c for c in rsps.calls if "/dishes/" in c.request.url]
        assert len(dish_calls) == 1

    @rsps.activate
    def test_get_pairings(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/dishes/ugali/pairings/",
            json={"pairings": []},
            status=200,
        )
        result = client.get_pairings("ugali")
        assert "pairings" in result

    @rsps.activate
    def test_get_substitutions(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/dishes/ugali/substitutions/",
            json={"substitutions": []},
            status=200,
        )
        result = client.get_substitutions("ugali")
        assert "substitutions" in result

    @rsps.activate
    def test_get_missing(self, client):
        rsps.add(
            rsps.POST,
            f"{BASE}/v1/dishes/ugali/missing/",
            json={"missing": []},
            status=200,
        )
        result = client.get_missing("ugali", ["ingredient-uuid-1"])
        assert "missing" in result


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRegions:
    @rsps.activate
    def test_get_regions(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/regions/",
            json={"results": [{"slug": "nairobi", "name_en": "Nairobi"}]},
            status=200,
        )
        result = client.get_regions()
        assert len(result["results"]) == 1

    @rsps.activate
    def test_get_regions_cached(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/regions/",
            json={"results": []},
            status=200,
        )
        client.get_regions()
        client.get_regions()
        assert len(rsps.calls) == 1


# ---------------------------------------------------------------------------
# Community submission (internal key)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCommunitySubmission:
    @rsps.activate
    def test_submit_community(self, client):
        rsps.add(
            rsps.POST,
            f"{BASE}/v1/internal/submissions/",
            json={"id": "engine-submission-uuid"},
            status=201,
        )
        result = client.submit_community({"name_en": "Test Recipe"})
        assert result["id"] == "engine-submission-uuid"
        # Verify internal key was used
        assert rsps.calls[0].request.headers["X-API-Key"] == client.internal_key


# ---------------------------------------------------------------------------
# Dataset diff
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDatasetDiff:
    @rsps.activate
    def test_get_dataset_diff(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/datasets/",
            json={"changed": [], "removed": []},
            status=200,
        )
        result = client.get_dataset_diff("2026.9.0")
        assert "changed" in result


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCircuitBreaker:
    def test_circuit_starts_closed(self, client):
        assert client._circuit_state() == "closed"

    def test_circuit_opens_after_threshold_failures(self, client):
        for _ in range(5):
            client._record_failure()
        assert client._circuit_state() == "open"

    def test_circuit_success_resets_failures(self, client):
        for _ in range(3):
            client._record_failure()
        client._record_success()
        assert client._circuit_state() == "closed"
        # Failure count should be reset
        from django.core.cache import cache as c

        assert c.get("ffconsumer:engine:circuit_failures") == 0

    @rsps.activate
    def test_open_circuit_raises_engine_unavailable(self, client):
        for _ in range(5):
            client._record_failure()
        from apps.engine_client.client import EngineUnavailableError

        with pytest.raises(EngineUnavailableError):
            client._get("/v1/some/path/")

    def test_circuit_transitions_to_half_open_after_recovery(self, client):
        import time

        from apps.engine_client.client import _CB_OPENED_AT, _CB_STATE

        cache.set(_CB_STATE, "open", timeout=None)
        # Simulate recovery period elapsed
        cache.set(_CB_OPENED_AT, time.time() - 31, timeout=None)  # > 30s
        state = client._circuit_state()
        assert state == "half_open"

    @rsps.activate
    def test_rate_limit_429_raises_engine_unavailable(self, client):
        rsps.add(
            rsps.GET,
            f"{BASE}/v1/health/",
            status=429,
            headers={"Retry-After": "30"},
        )
        from apps.engine_client.client import EngineUnavailableError

        with pytest.raises(EngineUnavailableError, match="rate limit"):
            client.health_ping()

    @rsps.activate
    def test_retry_on_network_error(self, client):
        """Client retries once on network errors."""
        rsps.add(rsps.GET, f"{BASE}/v1/health/", body=ConnectionError("net error"))
        rsps.add(rsps.GET, f"{BASE}/v1/health/", body=ConnectionError("net error"))
        from apps.engine_client.client import EngineUnavailableError

        with pytest.raises(EngineUnavailableError):
            client.health_ping()
        assert len(rsps.calls) == 2  # original + 1 retry

    @rsps.activate
    def test_no_retry_on_4xx(self, client):
        """Client does NOT retry on 4xx errors."""
        rsps.add(rsps.GET, f"{BASE}/v1/health/", status=404)
        import requests

        with pytest.raises(requests.HTTPError):
            client.health_ping()
        assert len(rsps.calls) == 1  # no retry


# ---------------------------------------------------------------------------
# Engine client tasks
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEngineClientTasks:
    @rsps.activate
    def test_poll_dataset_version_no_change(self):
        from apps.engine_client.tasks import check_dataset_drift

        rsps.add(
            rsps.GET,
            f"{BASE}/v1/meta/version/",
            json={"dataset_version": "2026.10.0"},
            status=200,
        )
        # Set the same version in cache so no change is detected
        cache.set("ffconsumer:engine:dataset_version", "2026.10.0", timeout=3600)
        # Should not raise
        check_dataset_drift()

    @rsps.activate
    def test_poll_dataset_version_version_change(self, mocker):
        from apps.engine_client.tasks import check_dataset_drift

        rsps.add(
            rsps.GET,
            f"{BASE}/v1/meta/version/",
            json={"dataset_version": "2026.11.0"},
            status=200,
        )
        mock_drift = mocker.patch(
            "apps.core.tasks.check_dataset_drift_saved_recipes.delay",
            return_value=None,
        )
        # Old version in cache
        cache.set("ffconsumer:engine:dataset_version", "2026.10.0", timeout=3600)
        check_dataset_drift()
        assert mock_drift.called
