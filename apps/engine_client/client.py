"""Typed engine API client for ff-consumer.

This is the ONLY place in the codebase that calls the Recipe Engine API.
No other module should import requests or httpx to call the engine directly.

Safety rules enforced here:
- Engine timeout: 5 seconds per call
- 1 retry on network error, no retry on 4xx
- Circuit breaker: open after 5 failures, half-open after 30 seconds
- On engine down: return cached result if available

The `diet` parameter on search() is REQUIRED and is checked at call time.
A missing diet list is a safety bug, not a configuration choice.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Circuit breaker Redis keys
_CB_STATE = "ffconsumer:engine:circuit_state"
_CB_FAILURES = "ffconsumer:engine:circuit_failures"
_CB_OPENED_AT = "ffconsumer:engine:circuit_opened_at"
_DATASET_VERSION_KEY = "ffconsumer:engine:dataset_version"

# Cache key prefixes
_SEARCH_PREFIX = "ffconsumer:search:"
_DISH_PREFIX = "ffconsumer:dish:"
_INGREDIENT_AC_PREFIX = "ffconsumer:ingredient_ac:"
_REGIONS_PREFIX = "ffconsumer:regions:"

# Cache TTLs in seconds
_SEARCH_TTL = 300       # 5 minutes
_DISH_TTL = 3600        # 1 hour
_INGREDIENT_AC_TTL = 600  # 10 minutes
_REGIONS_TTL = 86400    # 24 hours
_DATASET_VERSION_TTL = 3600  # 1 hour


class EngineUnavailableError(Exception):
    """Raised when the engine circuit is open and no cached result is available."""


class EngineClient:
    """Typed client wrapping all Recipe Engine API calls.

    Instantiate once per process (or use the module-level `engine` instance).
    All methods are synchronous.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        internal_key: str | None = None,
        timeout: float | None = None,
    ):
        self.base_url = (base_url or settings.ENGINE_BASE_URL).rstrip("/")
        self.api_key = api_key or settings.ENGINE_API_KEY
        self.internal_key = internal_key or settings.ENGINE_INTERNAL_KEY
        self.timeout = timeout or settings.ENGINE_TIMEOUT
        self._threshold = settings.ENGINE_CIRCUIT_BREAKER_THRESHOLD
        self._recovery = settings.ENGINE_CIRCUIT_BREAKER_RECOVERY

    # -------------------------------------------------------------------------
    # Circuit breaker helpers
    # -------------------------------------------------------------------------

    def _circuit_state(self) -> str:
        state = cache.get(_CB_STATE, "closed")
        if state == "open":
            opened_at = cache.get(_CB_OPENED_AT, 0)
            if time.time() - float(opened_at) >= self._recovery:
                cache.set(_CB_STATE, "half_open", timeout=None)
                return "half_open"
        return state

    def _record_success(self):
        cache.set(_CB_STATE, "closed", timeout=None)
        cache.set(_CB_FAILURES, 0, timeout=None)

    def _record_failure(self):
        failures = (cache.get(_CB_FAILURES) or 0) + 1
        cache.set(_CB_FAILURES, failures, timeout=None)
        if failures >= self._threshold:
            cache.set(_CB_STATE, "open", timeout=None)
            cache.set(_CB_OPENED_AT, time.time(), timeout=None)
            logger.error("Engine circuit opened after %d consecutive failures.", failures)

    # -------------------------------------------------------------------------
    # HTTP helpers
    # -------------------------------------------------------------------------

    def _headers(self, *, internal: bool = False) -> dict:
        key = self.internal_key if internal else self.api_key
        return {
            "X-API-Key": key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> dict:
        return self._request("GET", path, params=params)

    def _post(self, path: str, body: dict, *, internal: bool = False) -> dict:
        return self._request("POST", path, body=body, internal=internal)

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        body: dict | None = None,
        internal: bool = False,
    ) -> dict:
        state = self._circuit_state()
        if state == "open":
            raise EngineUnavailableError("Engine circuit is open.")

        url = f"{self.base_url}{path}"
        attempt = 0
        last_exc: Exception | None = None

        while attempt <= 1:  # 1 retry on network error
            try:
                resp = requests.request(
                    method,
                    url,
                    params=params,
                    json=body,
                    headers=self._headers(internal=internal),
                    timeout=self.timeout,
                )
                if resp.status_code == 429:
                    # Honour Retry-After but don't count as circuit failure
                    retry_after = resp.headers.get("Retry-After", "60")
                    raise EngineUnavailableError(
                        f"Engine rate limit. Retry after {retry_after}s."
                    )
                if resp.status_code >= 500:
                    raise requests.RequestException(
                        f"Engine server error: {resp.status_code}"
                    )
                resp.raise_for_status()
                self._record_success()
                return resp.json()
            except (
                requests.ConnectionError,
                requests.Timeout,
                requests.RequestException,
                ConnectionError,  # raised by test mocks and some network layers
                OSError,
            ) as exc:
                last_exc = exc
                attempt += 1
                if attempt > 1:
                    break
                # No retry on 4xx
                if hasattr(exc, "response") and exc.response is not None:
                    if exc.response.status_code < 500:
                        self._record_success()  # 4xx is a valid response
                        raise

        self._record_failure()
        raise EngineUnavailableError(f"Engine request failed: {last_exc}") from last_exc

    # -------------------------------------------------------------------------
    # Dataset version
    # -------------------------------------------------------------------------

    def get_dataset_version(self) -> str:
        """Return the current dataset version, cached for 1 hour."""
        cached = cache.get(_DATASET_VERSION_KEY)
        if cached:
            return cached
        try:
            data = self._get("/v1/meta/version/")
            version = data.get("dataset_version", "unknown")
            cache.set(_DATASET_VERSION_KEY, version, timeout=_DATASET_VERSION_TTL)
            return version
        except EngineUnavailableError:
            return cache.get(_DATASET_VERSION_KEY, "unknown")

    def refresh_dataset_version(self) -> str:
        """Force-refresh the dataset version and flush engine caches if changed."""
        cache.delete(_DATASET_VERSION_KEY)
        new_version = self.get_dataset_version()
        logger.info("Dataset version refreshed: %s", new_version)
        return new_version

    # -------------------------------------------------------------------------
    # Health / meta
    # -------------------------------------------------------------------------

    def health_ping(self) -> dict:
        return self._get("/v1/health/")

    def get_version(self) -> dict:
        return self._get("/v1/meta/version/")

    # -------------------------------------------------------------------------
    # Ingredient resolve and autocomplete
    # -------------------------------------------------------------------------

    def resolve(self, tokens: list[str], lang: str = "en") -> dict:
        """Turn free-text tokens into ingredient IDs.

        Always returns the full resolve response including ambiguous tokens.
        The caller must check for ambiguous tokens and surface choices to the
        user — never pass an ambiguous token straight to search().
        """
        return self._post(
            "/v1/ingredients/resolve",
            {"tokens": tokens, "lang": lang},
        )

    def get_ingredients(self, q: str, lang: str = "en") -> dict:
        """Autocomplete ingredient search. Results are cached."""
        cache_key = f"{_INGREDIENT_AC_PREFIX}{q}:{lang}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        result = self._get("/v1/ingredients/", params={"q": q, "lang": lang})
        cache.set(cache_key, result, timeout=_INGREDIENT_AC_TTL)
        return result

    # -------------------------------------------------------------------------
    # Search — SAFETY CRITICAL
    # -------------------------------------------------------------------------

    def search(
        self,
        ingredients: list[str],
        diet: list[str],
        mode: str = "strict",
        exclude: list[str] | None = None,
        lang: str = "en",
        limit: int = 20,
        meal_type: str | None = None,
    ) -> dict:
        """Call the engine search endpoint.

        SAFETY: `diet` must always be populated from the user's profile_diet.
        An empty list is allowed only for users with no diet restrictions,
        not as a default or shortcut.
        """
        if diet is None:
            raise ValueError(
                "diet must be provided (pass [] for users with no restrictions, "
                "never None). This prevents allergen exclusions from being silently dropped."
            )

        dataset_version = self.get_dataset_version()
        cache_key = _search_cache_key(ingredients, diet, mode, dataset_version)

        cached = cache.get(cache_key)
        if cached:
            return cached

        state = self._circuit_state()
        if state == "open":
            # Return degraded response if circuit is open
            return {"engine_status": "degraded", "results": {}, "dataset_version": dataset_version}

        body: dict[str, Any] = {
            "ingredients": ingredients,
            "diet": diet,
            "mode": mode,
            "lang": lang,
            "limit": limit,
        }
        if exclude:
            body["exclude"] = exclude
        if meal_type:
            body["meal_type"] = meal_type

        try:
            result = self._post("/v1/search/by-ingredients", body)
            cache.set(cache_key, result, timeout=_SEARCH_TTL)
            return result
        except EngineUnavailableError:
            # Return degraded, not an error
            return {
                "engine_status": "degraded",
                "results": {},
                "dataset_version": dataset_version,
            }

    # -------------------------------------------------------------------------
    # Dishes
    # -------------------------------------------------------------------------

    def get_dish(self, slug: str, lang: str = "en") -> dict:
        """Fetch dish detail, cached per slug+dataset_version."""
        dataset_version = self.get_dataset_version()
        cache_key = f"{_DISH_PREFIX}{slug}:{dataset_version}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        result = self._get(f"/v1/dishes/{slug}/", params={"lang": lang})
        cache.set(cache_key, result, timeout=_DISH_TTL)
        return result

    def get_pairings(self, slug: str) -> dict:
        return self._get(f"/v1/dishes/{slug}/pairings/")

    def get_substitutions(self, slug: str) -> dict:
        return self._get(f"/v1/dishes/{slug}/substitutions/")

    def get_missing(self, slug: str, pantry_ingredient_ids: list[str]) -> dict:
        return self._post(
            f"/v1/dishes/{slug}/missing/",
            {"pantry": pantry_ingredient_ids},
        )

    # -------------------------------------------------------------------------
    # Regions
    # -------------------------------------------------------------------------

    def get_regions(self, lang: str = "en") -> dict:
        """Fetch regions list, cached for 24 hours."""
        cache_key = f"{_REGIONS_PREFIX}{lang}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        result = self._get("/v1/regions/", params={"lang": lang})
        cache.set(cache_key, result, timeout=_REGIONS_TTL)
        return result

    # -------------------------------------------------------------------------
    # Community submissions (internal key)
    # -------------------------------------------------------------------------

    def submit_community(self, payload: dict) -> dict:
        """Forward an approved community submission to the engine.

        Uses the internal key (internal:curation scope).
        This must only be called from a Celery worker after moderation approval.
        """
        return self._post("/v1/internal/submissions/", payload, internal=True)

    # -------------------------------------------------------------------------
    # Dataset diff (for nightly drift check)
    # -------------------------------------------------------------------------

    def get_dataset_diff(self, since_version: str) -> dict:
        return self._get("/v1/datasets/", params={"since": since_version})


def _search_cache_key(
    ingredients: list[str],
    diet: list[str],
    mode: str,
    dataset_version: str,
) -> str:
    """Build a deterministic cache key for a search request."""
    payload = json.dumps(
        {
            "ingredients": sorted(ingredients),
            "diet": sorted(diet),
            "mode": mode,
            "dataset_version": dataset_version,
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return f"{_SEARCH_PREFIX}{digest}"


# ---------------------------------------------------------------------------
# Module-level singleton — import and use this everywhere
# ---------------------------------------------------------------------------
engine = EngineClient()
