# Engine API Contract

## Authentication

Every request to the engine must carry:
```
X-API-Key: <key>
```

Keys are stored in the secret manager, never in code or the app.
Two keys needed at launch:
- `ENGINE_API_KEY` — scopes `read:search`, `read:catalog`
- `ENGINE_INTERNAL_KEY` — scope `internal:curation` (community submissions only)

Key format: `ffk_<40 hex chars>`  
Prefix (first 8 chars) is used for fast DB lookup on the engine side.

## Base URL

```
https://engine.flavorfind.co.ke/v1/
```

## All Endpoints

### Health / Meta

```
GET  /v1/health/           → {status, version, dataset_version}
GET  /v1/meta/version/     → {engine_version, dataset_version}
```

Pin `dataset_version` from `/v1/meta/version/` on startup and cache it.
Use it as part of all cache keys. When it changes, flush all engine response caches.

---

### Ingredients

```
GET  /v1/ingredients/              → list (autocomplete, debounced)
     ?q=<str>                       fuzzy search
     ?lang=en|sw

GET  /v1/ingredients/<slug>/       → single ingredient detail

POST /v1/ingredients/resolve       → resolve free-text tokens to ingredient IDs
```

**POST /v1/ingredients/resolve** — use this before search when the user types free text.
Handles spelling, aliases (sukuma wiki = kale), Swahili/Sheng names.

Response per token:
```json
{
  "token": "unga",
  "status": "ambiguous",        // matched | ambiguous | unmatched
  "ingredient_id": null,
  "method": "alias",
  "confidence": 0.7
}
```

**Rule:** if any token comes back `ambiguous`, show the user a choice picker. Never guess.
The backend must never pass an ambiguous token straight to search.

---

### Search

```
POST /v1/search/by-ingredients
```

Required scope: `read:search`

Request body:
```json
{
  "ingredients": ["tomato", "onion", "sukuma"],   // 1–30 strings
  "exclude": [],                                   // ingredient slugs to exclude
  "mode": "strict",                                // "strict" | "explore"
  "meal_type": null,                               // breakfast|lunch|dinner|snack|dessert|drink|any
  "course": null,                                  // starter|main|side|dessert|drink|snack|condiment
  "lang": "en",                                    // "en" | "sw"
  "limit": 20,                                     // 1–50 per tier
  "diet": ["vegetarian", "gluten-free"]            // diet tag slugs (allergen exclusions)
}
```

**SAFETY RULE:** `diet` must always be populated from the user's profile.
A user with allergen exclusions in their profile can NEVER trigger a search without those exclusions in `diet`.
This is a hard requirement — failure here is a safety bug, not a feature gap.

Response envelope:
```json
{
  "dataset_version": "2026.10.0",
  "mode": "strict",
  "candidate_count": 240,
  "total_results": 12,
  "resolved": [...],           // how each input token was understood
  "ambiguous": ["unga"],       // tokens that need clarification
  "unmatched": ["xyz"],        // tokens not found
  "results": {
    "exact":    [...],         // all required ingredients present
    "can_make": [...],         // all required + staples assumed
    "almost":   [...]          // explore mode only: 1–2 missing
  }
}
```

Each result item:
```json
{
  "dish_id": "uuid",
  "slug": "ugali-sukuma",
  "name_en": "Ugali with Sukuma Wiki",
  "name_sw": "Ugali na Sukuma",
  "tier": "exact",
  "score": 0.92,
  "score_breakdown": {"coverage": 0.9, "popularity": 0.85, ...},
  "matched": [{"id": "...", "slug": "sukuma", "name_en": "Sukuma Wiki", "name_sw": "Sukuma"}],
  "missing": [],
  "unused": [],
  "assumed_staples": [],
  "quality_level": "verified"
}
```

---

### Dishes

```
GET  /v1/dishes/                   → catalogue (paginated)
     ?region=<slug>
     ?meal_type=breakfast|lunch|dinner|snack|dessert|drink|any
     ?diet=<slug>
     ?lang=en|sw

GET  /v1/dishes/<slug>/            → dish detail (ingredients, steps, nutrition, tags)

GET  /v1/dishes/<slug>/pairings/   → suggested pairings by type and strength

GET  /v1/dishes/<slug>/substitutions/ → substitutions with quality grade

POST /v1/dishes/<slug>/missing/    → given user pantry, what's missing to make this dish
```

Required scope: `read:catalog`

Dish detail includes: `name_en`, `name_sw`, `description`, `cuisine_tags`, `diet_tags`,
`meal_type`, `course`, `region_slug`, `cost_estimate_kes`, `nutrition` (calories, protein, etc.
labelled as estimates), `required_ingredients`, `optional_ingredients`, `steps`.

Cache dish detail with ETag. The engine sets `Cache-Control: private, max-age=300`.

**Allergen text rule:** any response that includes allergen or dietary information must display:
> "Allergen information is for guidance only. Always confirm with the kitchen before ordering."

---

### Regions

```
GET  /v1/regions/    → list of region slugs and names (en + sw)
```

Used to populate the "Taste of 47 counties" content page and filter dishes by region.

---

### Community Submissions (internal key only)

```
POST /v1/internal/submissions/
```

Required scope: `internal:curation`  
Use `ENGINE_INTERNAL_KEY` for this call only.

This is called by a Celery worker (not directly from a user request) after a submission
passes the consumer backend's own moderation queue.

---

### Dataset Diff (for cache invalidation)

```
GET  /v1/datasets/?since=<dataset_version>
```

Returns changed/removed dish IDs since the given version.
Use this in a nightly Celery beat task to flag stale saved recipes.

---

## Caching Rules

```
cache key = sha256(sorted(ingredients) + mode + diet + dataset_version)
```

- Cache TTL: 5 minutes for search results, 1 hour for dish detail
- Bust entire engine cache when `dataset_version` changes
- Use Django's Redis cache backend, key prefix `ffconsumer_engine:`
- Respect ETag from dish detail responses

## Resilience Rules

- Timeout: 5 seconds per engine call
- Retries: 1 retry on network error, no retry on 4xx
- Circuit breaker: open after 5 consecutive failures, half-open after 30 seconds
- On engine down: serve cached results and saved recipes, add `"engine_status": "degraded"` to response
- On 429: honour `Retry-After` header, surface to user as "try again in X seconds"

## Contract Safety

- The engine client is generated from the engine OpenAPI schema (`/v1/schema/`)
- CI must run `oasdiff` to detect breaking changes
- Engine v1 is additive-only — the backend must ignore unknown fields (don't use strict deserialisation)
- Store `dataset_version` with every saved recipe so drift can be detected

## What the Engine Does NOT Know

- User IDs or emails
- Device tokens or platform info
- Subscription status
- Pantry quantities (engine ignores quantities in v1 — keep them only as notes)
- Pricing beyond cost estimates (which are always labelled as estimates)
