# Consumer Backend Architecture

## Django Apps

Build these apps in this order (matches the sprint plan):

| App | Responsibility |
|---|---|
| `core` | Base models (UUID pk, timestamps, soft delete), pagination, error format, request ID middleware, permissions |
| `accounts` | Users, login methods (email+password, phone OTP), sessions, devices, consent records, account deletion/export |
| `profiles` | Language (en/sw), household size, diet tags, allergen exclusions, region preference, budget KES/meal |
| `engine_client` | Typed client wrapping the engine API — retries, timeouts, circuit breaker, dataset-version cache, ambiguity helper |
| `pantry` | Pantry items (engine ingredient IDs + display names), staples overrides |
| `library` | Saved recipes (engine dish_id + slug + dataset_version), collections, cooking history, notes |
| `planner` | Weekly meal plans, servings per dish, shopping lists, WhatsApp share text |
| `budget` | Budget mode — filters engine cost estimates by user's KES budget per meal |
| `content` | Taste of 47 counties: editorial stories, photos, region slugs keyed to engine regions |
| `community` | Recipe submissions (drafts → engine), submission status tracking, reviews and ratings |
| `billing` | Plans (Free/Plus), Flavor Find Plus at KES 199/month, M-Pesa Daraja STK push, receipts, entitlements |
| `notifications` | Push, email, in-app; preferences; quiet hours |
| `partners` | Sponsored slots and affiliate hooks (clearly labelled to users) |
| `sync` | Offline change queue for Android app, conflict resolution rules |
| `moderation` | Review queue for submissions and reviews, audit trail |
| `api` | Versioned routers (`/v1` public, `/internal` staff), OpenAPI schema |

## URL Structure

```
/v1/                    ← public API (JWT auth for users, open for public endpoints)
/v1/auth/               ← register, login, OTP, refresh, logout
/v1/me/                 ← profile, diet, export, delete
/v1/pantry/             ← pantry CRUD
/v1/search/             ← wraps engine search + pantry context
/v1/resolve/            ← wraps engine ingredient resolve
/v1/saved/              ← saved recipes, collections
/v1/cooked/             ← cooking history
/v1/plans/              ← meal plans + shopping lists
/v1/budget/             ← budget mode suggest
/v1/regions/            ← Taste of 47 counties
/v1/stories/            ← editorial content
/v1/submissions/        ← community recipe submissions
/v1/dishes/<slug>/reviews/  ← reviews
/v1/plans/              ← billing plans
/v1/subscribe/          ← M-Pesa STK push
/v1/subscription/       ← current subscription status
/v1/mpesa/callback/     ← M-Pesa webhook (unauthenticated, verified by signature)
/v1/devices/            ← push token registration
/v1/sync/push           ← offline sync
/v1/sync/pull           ← offline sync
/v1/meta/version/       ← backend version + engine dataset_version
/v1/health/             ← health check

/admin/                 ← Django admin (separate address in prod, 2FA mandatory)
```

## Data Model — Own Database

**No food tables.** If it describes a dish, ingredient, or pairing, it lives in the engine.

### Identity / Auth

```
user
  id (UUID PK), email (unique), phone (nullable, unique), 
  password_hash (Argon2id), language (en|sw), status (active|suspended|deleted),
  created_at, updated_at, deleted_at (soft delete)

auth_identity
  user_id FK, provider (password|phone_otp|google), 
  provider_uid (nullable), verified_at

device
  user_id FK, platform (android|ios|web), push_token, 
  last_seen, created_at

consent
  user_id FK, type (terms|privacy|marketing), 
  version, granted_at, revoked_at
```

### Profiles

```
profile
  user_id FK (1:1), household_size (int), region_slug, 
  budget_kes_per_meal (nullable), updated_at

profile_diet
  user_id FK, diet_tag_slug, source (user_set|allergen)
  -- examples: vegetarian, gluten-free, nut-free, halal, contains-pork
  -- allergen tags stored here MUST be sent on every engine search call
```

### Pantry

```
pantry_item
  id (UUID), user_id FK, ingredient_id (engine UUID), 
  ingredient_slug (engine slug), display_name (cached from engine),
  added_at, expires_on (nullable)
  -- quantities NOT stored (engine ignores them in v1)
  -- display_name refreshed when dataset_version changes
```

### Library

```
saved_recipe
  id (UUID), user_id FK, dish_id (engine UUID), dish_slug,
  dataset_version (version when saved), collection_id FK (nullable),
  note (text), saved_at

collection
  id (UUID), user_id FK, name, created_at

cook_log
  id (UUID), user_id FK, dish_id, cooked_at, rating (1–5, nullable)
```

### Planner

```
meal_plan
  id (UUID), user_id FK, week_start (date), created_at

meal_plan_entry
  id (UUID), plan_id FK, day (mon–sun), meal_type (breakfast|lunch|dinner|snack),
  dish_id (engine UUID), dish_slug, servings (int), note

shopping_list
  id (UUID), user_id FK, plan_id FK (nullable), created_at

shopping_item
  id (UUID), list_id FK, ingredient_id, ingredient_slug, display_name,
  quantity_note (text, e.g. "500g"), checked (bool), 
  price_estimate_kes (nullable, from engine cost data)
```

### Community

```
submission
  id (UUID), user_id FK, payload (JSON — the raw submission),
  engine_submission_id (nullable — set after forwarding to engine),
  status (draft|sent|in_review|accepted|rejected), reason (text),
  created_at, updated_at

review
  id (UUID), user_id FK, dish_id (engine UUID), dish_slug,
  stars (1–5), text (text), status (pending|approved|rejected),
  created_at
```

### Billing

```
plan
  code (PK, e.g. "free"|"plus"), name, price_kes (0 for free),
  features (JSON), created_at

subscription
  id (UUID), user_id FK (unique), plan_id FK,
  status (active|trialing|cancelled|expired),
  trial_ends_at, renews_at, cancelled_at, created_at

payment
  id (UUID), user_id FK, subscription_id FK,
  provider (mpesa), provider_ref (M-Pesa transaction ID),
  amount_kes, status (pending|confirmed|failed),
  receipt_no, created_at, confirmed_at
```

### Ops

```
engine_cache
  key (SHA256 of input + dataset_version), response (JSON),
  fetched_at, expires_at
  -- complement to Redis; for durable cache across restarts

audit_event
  id (UUID), actor_id (user or staff), actor_type,
  action (e.g. delete_account, approve_submission),
  object_type, object_id, before (JSON), after (JSON),
  reason, ip_address, created_at
  -- append-only, shipped to external log store

change_log
  same structure as audit_event — for user-visible history
```

## Auth Architecture

### End users
- Registration: email + password (Argon2id) or phone number
- Login: email+password or phone OTP (6-digit, 5-minute TTL, max 5 attempts)
- Tokens: short-lived JWT access token (15 min) + rotating refresh token (30 days, stored in DB for revocation)
- Optional 2FA: TOTP authenticator app for Plus users
- Device list visible in settings; remote logout revokes all tokens for a device

### Staff (admin)
- Django session auth via `django-two-factor-auth`
- **Mandatory** TOTP or hardware key — no SMS/email codes
- Admin served at a separate address, behind VPN or IP allowlist in production
- Step-up confirmation for: account deletion, submission approve/reject, billing changes

### Public endpoints (no auth required)
- `GET /v1/health/`
- `GET /v1/meta/version/`
- `GET /v1/regions/`
- `GET /v1/stories/` and `GET /v1/stories/<slug>/`
- `GET /v1/dishes/<slug>/` (basic dish info, no personalisation)
- `POST /v1/mpesa/callback/` (verified by signature, not by user auth)

### Personalisation requires auth
- Search with pantry context
- Saved recipes, meal plans, shopping lists
- Community submissions and reviews
- Billing and subscriptions
- Sync

## Free vs Plus Gating

| Feature | Free | Plus (KES 199/month) |
|---|---|---|
| Search (engine) | ✅ unlimited | ✅ |
| Dish pages + regions | ✅ | ✅ |
| Pantry | ✅ | ✅ |
| Save recipes (up to 20) | ✅ | Unlimited |
| Community submissions | ✅ | ✅ |
| Meal plans | ❌ | ✅ |
| Shopping lists | ❌ | ✅ |
| Nutrition details | ❌ | ✅ |
| Budget mode | ❌ | ✅ |
| Offline sync | ❌ | ✅ |
| AI cooking buddy | ❌ | Stage 4 |
| Ads | Yes | No |

## Payments (M-Pesa Daraja)

- Flow: `POST /v1/subscribe/` → backend calls Daraja STK push API → user gets prompt on phone → user confirms → Daraja calls `POST /v1/mpesa/callback/`
- Callback is unauthenticated but verified: check source IP is Safaricom's range AND verify signature
- Amounts re-checked server-side — never trust the callback amount alone
- Idempotent: use `provider_ref` as idempotency key; duplicate callbacks are silently ignored
- No card data stored ever
- Sandbox for staging: `https://sandbox.safaricom.co.ke/`

## Engine Client App

The `engine_client` app is the single place all engine calls go through. It must:

```python
# Pseudo-structure for apps/engine_client/client.py

class EngineClient:
    base_url: str           # from settings.ENGINE_BASE_URL
    api_key: str            # from settings.ENGINE_API_KEY (secret manager)
    internal_key: str       # from settings.ENGINE_INTERNAL_KEY
    timeout: float = 5.0
    dataset_version: str    # cached from /v1/meta/version/ on startup
    
    def search(self, ingredients, mode, diet, exclude, lang, limit) -> SearchResponse
    def resolve(self, tokens, lang) -> ResolveResponse
    def get_dish(self, slug, lang) -> DishDetail
    def get_pairings(self, slug) -> PairingsResponse
    def get_substitutions(self, slug) -> SubstitutionsResponse
    def get_missing(self, slug, pantry_ingredient_ids) -> MissingResponse
    def get_ingredients(self, q, lang) -> list[Ingredient]
    def get_regions(self) -> list[Region]
    def get_version(self) -> VersionResponse
    def submit_community(self, payload) -> SubmissionResponse  # uses internal_key
```

Circuit breaker state lives in Redis:
```
ffconsumer_engine:circuit_state  → "closed" | "open" | "half_open"
ffconsumer_engine:circuit_failures → int (consecutive failures)
ffconsumer_engine:circuit_opened_at → timestamp
```

## Offline Sync (Android)

- Android app stores changes locally in SQLite with `change_id` (UUID) and `changed_at`
- `POST /v1/sync/push` — client sends array of changes; server applies, returns conflicts
- `GET /v1/sync/pull?since=<timestamp>` — server returns changes since last sync
- Conflict rule: server wins for shared data; user wins for pantry and notes
- Sync state per device stored in `device` table: `last_sync_at`

## Caching Strategy

| Data | Cache TTL | Key |
|---|---|---|
| Engine search results | 5 min | `search:{sha256(inputs+diet+dataset_version)}` |
| Dish detail | 1 hour | `dish:{slug}:{dataset_version}` |
| Ingredient autocomplete | 10 min | `ingredient_ac:{q}:{lang}` |
| Engine dataset_version | 1 hour | `engine:dataset_version` |
| Regions list | 24 hours | `regions:{lang}` |

All keys prefixed with `ffconsumer:`.
Flush `ffconsumer:search:*` and `ffconsumer:dish:*` when dataset_version changes.
