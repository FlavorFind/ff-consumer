# FLAVOR FIND | ARCHITECTURE DOCUMENT

## Consumer Backend — Sprint Architecture
### Full architecture, security, CI/CD and build plan for the consumer backend

**Architecture | Data model | Auth | API | Payments | Sync**
**Repository setup | CI/CD pipelines | Security | 2FA | Operations | Iteration plan**

*Draft v1 | October 2026 | Nairobi, Kenya | Confidential*

---

## 1. What We Build Here, and Why

The engine is live. The consumer backend is next. Here is the reasoning, so it is a decision and not a habit.

- **It is the product.** The consumer website and Android app cannot exist without it. Users, pantries, meal plans, subscriptions — all of it lives here.
- **It is the data bridge.** The engine knows food; this backend knows people. It joins the two without mixing them.
- **It is the revenue layer.** Flavor Find Plus at KES 199/month, M-Pesa payments, and sponsored content all run through here.
- **It is the trust layer.** Allergen safety, consent, data export, account deletion, privacy — none of that exists in the engine. It all lives here.
- **The engine is ready.** Engine v1.0.0 is live at `https://engine.flavorfind.co.ke`. The consumer backend calls it as a client. Nothing is blocked.

This document is the technical architecture and operating plan for the consumer backend (`ff-consumer`): data model, repository setup, CI/CD, security, 2FA, infrastructure, and the full five-iteration plan.

The companion document, **Consumer Backend Blueprint**, explains in plain language how each part of the consumer backend works, the 47 build steps, and the test strategy.

---

## 2. Scope and Success Criteria

### In scope

| Area | What |
|---|---|
| Identity | Registration, email+password login, phone OTP login, JWT tokens, device management, consent |
| Profiles | Language, household size, diet tags, allergen exclusions, region preference, budget |
| Pantry | CRUD for pantry items keyed to engine ingredient IDs |
| Search | Wraps engine search, injects pantry + profile diet, personalisation layer |
| Library | Saved recipes, collections, cooking history, notes |
| Planner | Weekly meal plans, shopping lists, WhatsApp share |
| Budget | Budget mode on top of engine cost estimates |
| Content | Taste of 47 counties stories and region pages |
| Community | Recipe submissions, reviews, moderation queue |
| Billing | Flavor Find Plus, M-Pesa Daraja STK push, entitlements |
| Notifications | Push, email, in-app, preferences |
| Sync | Offline change queue for Android, conflict resolution |
| Engine client | Typed client, circuit breaker, cache, ambiguity helper |
| API | `/v1/` router, OpenAPI schema, TypeScript + Kotlin generated clients |
| Ops | CI/CD, staging, monitoring, runbooks |

### Out of scope

- Hotel platform and tenant databases
- LLM / AI cooking buddy (Stage 4)
- Image hosting beyond avatars
- Native iOS app (PWA + Android APK first)
- Affiliate checkout (hooks only in v1)
- Machine-learning recommendations

### Success criteria (targets, not promises)

| Area | Target at v1.0 |
|---|---|
| Auth | Register, login (email+password and phone OTP), JWT, logout — all working; OTP tested for replay and brute-force |
| Safety | Safety golden set at 100%: vegetarian profile never returns meat; excluded allergen never appears in search results |
| Search | Search p95 < 250 ms through the backend at 50 req/s on staging (engine < 150 ms + consumer overhead) |
| Payments | M-Pesa sandbox callback: duplicate, wrong amount, timeout — all handled; Plus activates correctly |
| Data | Every row scoped to its owner; automated permission tests verify no cross-user access |
| Coverage | 85% overall; 95% for `accounts`, `billing`, `engine_client` |
| API | OpenAPI complete; TypeScript client compiles; Kotlin client compiles; app teams integrate in under a day |
| Security | 2FA on every staff account; no open high/critical; pen test findings fixed; go-live checklist signed |
| Privacy | Consent records, export endpoint, deletion endpoint, privacy notice, breach procedure in place |
| Ops | Rollback drill and restore drill passed; dashboards and alerts live; runbooks complete |

---

## 3. System Context

The consumer backend is a middleware layer. It never reads the engine's database.

```
Website / Android app
        │
        ▼
  Caddy (TLS, WAF)
        │
        ▼
  Consumer API (Django + DRF)    ──────────►  Recipe Engine /v1
  ┌─────────────────────────┐    X-API-Key      (read:search, read:catalog)
  │ accounts, profiles      │
  │ pantry, library         │    ──────────►  Recipe Engine /internal
  │ planner, billing        │    X-Internal-Key  (internal:curation)
  │ community, sync         │
  └─────────────────────────┘
        │                  │
        ▼                  ▼
  PostgreSQL (own DB)   Redis 7
  (never shared with    (cache, rate
   engine DB)           limits, queue)
        │
        ▼
  Celery worker + beat
  (sync, notifications, billing, drift check)

Staff (moderators, admins) ──► Django admin
                                (separate address, 2FA, VPN/allowlist)
```

**The two-system rule:**
- The consumer backend calls the engine. It never reads the engine database.
- The engine never knows user IDs, emails, device tokens, or subscription status.
- Diet and allergen exclusions are always sent on every search — no exceptions.

---

## 4. Logical Architecture

Four layers. Views stay thin, business logic lives in services, database reads live in selectors.

```
REQUEST FLOW: TOP TO BOTTOM

API LAYER (DRF)
  Auth API  │  Profile API  │  Search API  │  Billing API  │  Sync API  │  …

CROSS-CUTTING
  JWT auth  │  Rate limits  │  Request ID  │  Entitlements  │  Audit log

SERVICE LAYER
  AuthService  │  SearchService  │  BillingService  │  SyncService  │  EngineClient

DOMAIN AND DATA ACCESS
  User  │  Profile  │  Pantry  │  Library  │  Plan  │  Submission  │  Subscription

STORAGE
  PostgreSQL 16          Redis 7               Engine API
  (own, private)         (cache, queue)        (HTTPS only)
```

### Django apps and their responsibilities

| App | Responsibility |
|---|---|
| `core` | Base models (UUID PK, timestamps, soft delete), pagination, error format, request ID middleware, custom exception handler, permissions |
| `accounts` | Users, email+password login, phone OTP login, JWT access + refresh tokens, device management, consent records, export, deletion |
| `profiles` | Language (en/sw), household size, diet tags, allergen exclusions, region preference, budget KES/meal |
| `engine_client` | Typed client for all engine calls — retries, timeouts, circuit breaker, dataset-version cache, ambiguity helper |
| `pantry` | Pantry items (engine ingredient IDs + display names), staples overrides |
| `library` | Saved recipes, collections, cooking history, notes |
| `planner` | Weekly meal plans, servings, shopping lists, WhatsApp share text |
| `budget` | Budget mode — filters engine cost estimates by user KES budget |
| `content` | Taste of 47 counties: stories, editorial, region slugs keyed to engine regions |
| `community` | Recipe submissions (drafts), status tracking, reviews and ratings |
| `billing` | Plans (Free/Plus), M-Pesa Daraja STK push, callbacks, receipts, entitlements |
| `notifications` | Push, email, in-app; preferences; quiet hours |
| `partners` | Sponsored slots and affiliate hooks, clearly labelled |
| `sync` | Offline change queue for Android, conflict resolution |
| `moderation` | Admin review queue for submissions and reviews, audit trail |
| `api` | Versioned routers (`/v1/` public, `/internal/` staff), OpenAPI schema |

---

## 5. Data Model (own database — no food tables)

### Design decisions

- **No food tables.** Every dish, ingredient, pairing, and substitution lives in the engine. The consumer DB stores references (slugs, IDs, `dataset_version`) only.
- **UUID primary keys** on all tables, matching the engine's pattern.
- **Soft delete** with `deleted_at`; nothing is permanently lost immediately.
- **Row-level scoping**: every queryset is filtered by `user=request.user`. Automated tests verify this.
- **`dataset_version` stored** on every saved recipe so drift can be detected.
- **Append-only audit log** shipped to an external store.

### Identity / Auth

```
user
  id (UUID PK)
  email (unique, nullable — phone-only users may have none initially)
  phone (unique, nullable, field-level encrypted)
  password_hash (Argon2id; nullable for phone-only accounts)
  language (en | sw, default en)
  status (active | suspended | deleted)
  is_staff (bool)
  is_superuser (bool)
  created_at, updated_at, deleted_at (soft delete)

auth_identity
  id (UUID PK)
  user_id FK → user
  provider (password | phone_otp | google)
  provider_uid (nullable)
  verified_at (nullable)
  created_at

device
  id (UUID PK)
  user_id FK → user
  platform (android | ios | web)
  push_token (nullable)
  last_seen
  last_sync_at (nullable)
  created_at

consent
  id (UUID PK)
  user_id FK → user
  type (terms | privacy | marketing)
  version (string, e.g. "2026-10")
  granted_at
  revoked_at (nullable)
```

### Profiles

```
profile
  id (UUID PK)
  user_id FK → user (unique, 1:1)
  household_size (int, default 1)
  region_slug (nullable — engine region slug)
  budget_kes_per_meal (decimal, nullable)
  updated_at

profile_diet
  id (UUID PK)
  user_id FK → user
  diet_tag_slug (string — engine dietary tag slug, e.g. "vegetarian", "nut-free")
  source (user_set | allergen)
  -- allergen rows MUST be sent on every engine search call
  created_at
```

### Pantry

```
pantry_item
  id (UUID PK)
  user_id FK → user
  ingredient_id (engine UUID)
  ingredient_slug (engine slug)
  display_name (cached from engine; refreshed on dataset_version change)
  added_at
  expires_on (nullable)
  -- quantities NOT stored (engine ignores them in v1)
```

### Library

```
saved_recipe
  id (UUID PK)
  user_id FK → user
  dish_id (engine UUID)
  dish_slug (engine slug)
  dataset_version (version when saved — for drift detection)
  collection_id FK → collection (nullable)
  note (text, nullable)
  saved_at

collection
  id (UUID PK)
  user_id FK → user
  name (string)
  created_at, updated_at

cook_log
  id (UUID PK)
  user_id FK → user
  dish_id (engine UUID)
  dish_slug
  cooked_at
  rating (int 1–5, nullable)
  note (text, nullable)
```

### Planner

```
meal_plan
  id (UUID PK)
  user_id FK → user
  week_start (date — always a Monday; identified externally as YYYY-Www)
  created_at, updated_at

meal_plan_entry
  id (UUID PK)
  plan_id FK → meal_plan
  day (mon | tue | wed | thu | fri | sat | sun)
  meal_type (breakfast | lunch | dinner | snack)
  dish_id (engine UUID)
  dish_slug
  servings (int, default 1)
  note (text, nullable)
  position (int — ordering within day+meal_type)

shopping_list
  id (UUID PK)
  user_id FK → user
  plan_id FK → meal_plan (nullable — can be created without a plan)
  name (string, nullable)
  created_at, updated_at

shopping_item
  id (UUID PK)
  list_id FK → shopping_list
  ingredient_id (engine UUID)
  ingredient_slug
  display_name
  quantity_note (text, e.g. "500g" — human note, not machine quantity)
  checked (bool, default false)
  price_estimate_kes (decimal, nullable — from engine cost data, labelled estimate)
  position (int)
```

### Community

```
submission
  id (UUID PK)
  user_id FK → user
  payload (JSON — raw submission fields)
  engine_submission_id (engine UUID, nullable — set after forwarding)
  status (draft | sent | in_review | accepted | rejected)
  reason (text, nullable — rejection reason)
  created_at, updated_at

review
  id (UUID PK)
  user_id FK → user
  dish_id (engine UUID)
  dish_slug
  stars (int 1–5)
  text (text, nullable)
  status (pending | approved | rejected)
  reason (text, nullable)
  created_at, updated_at
```

### Billing

```
plan
  code (PK, e.g. "free" | "plus")
  name (string)
  price_kes (decimal, 0 for free)
  features (JSON — list of feature keys)
  created_at

subscription
  id (UUID PK)
  user_id FK → user (unique — one active subscription per user)
  plan_id FK → plan
  status (active | trialing | cancelled | expired)
  trial_ends_at (nullable)
  renews_at (nullable)
  cancelled_at (nullable)
  created_at, updated_at

payment
  id (UUID PK)
  user_id FK → user
  subscription_id FK → subscription
  provider (mpesa)
  provider_ref (M-Pesa transaction ID — idempotency key, unique)
  amount_kes (decimal — re-verified server-side, never from callback alone)
  status (pending | confirmed | failed)
  receipt_no (string, nullable)
  created_at
  confirmed_at (nullable)
```

### Partners and Notifications

```
sponsored_slot
  id (UUID PK)
  partner_name (string)
  dish_id (engine UUID, nullable)
  ingredient_id (engine UUID, nullable)
  label (string — shown to users, e.g. "Sponsored")
  starts_at, ends_at
  active (bool)

notification
  id (UUID PK)
  user_id FK → user
  channel (push | email | in_app)
  type (string — e.g. "meal_reminder", "recipe_approved")
  title, body (string)
  data (JSON, nullable)
  read_at (nullable)
  sent_at (nullable)
  created_at

notification_preference
  id (UUID PK)
  user_id FK → user (unique)
  push_enabled (bool, default true)
  email_enabled (bool, default true)
  quiet_hours_start (time, nullable)
  quiet_hours_end (time, nullable)
  updated_at
```

### Ops

```
audit_event
  id (UUID PK)
  actor_id (UUID — user or staff)
  actor_type (user | staff)
  action (string — e.g. "delete_account", "approve_submission", "payment_confirmed")
  object_type (string, nullable)
  object_id (UUID, nullable)
  before_data (JSON, nullable)
  after_data (JSON, nullable)
  reason (text, nullable)
  ip_address (inet, nullable)
  created_at
  -- append-only; never updated or deleted; shipped to external log store

engine_cache
  key (VARCHAR 64 — SHA256 of inputs + dataset_version)
  response (JSON)
  fetched_at
  expires_at
  -- durable complement to Redis; survives restarts
```

---

## 6. Engine Client Architecture

The `engine_client` app is the **single and only place** all engine calls originate from. Nothing else imports `requests` to call the engine.

```python
# Pseudo-structure: apps/engine_client/client.py

class EngineClient:
    base_url: str          # settings.ENGINE_BASE_URL
    api_key: str           # settings.ENGINE_API_KEY (secret manager)
    internal_key: str      # settings.ENGINE_INTERNAL_KEY (secret manager)
    timeout: float = 5.0
    dataset_version: str   # cached from /v1/meta/version/ on startup, Redis TTL 1h

    # Core methods
    def get_version(self) -> VersionResponse
    def health_ping(self) -> HealthResponse

    # Search
    def search(self, ingredients, mode, diet, exclude, lang, limit) -> SearchResponse
    def resolve(self, tokens, lang) -> ResolveResponse
    def get_ingredients(self, q, lang) -> list[Ingredient]   # autocomplete

    # Catalog
    def get_dish(self, slug, lang) -> DishDetail
    def get_pairings(self, slug) -> PairingsResponse
    def get_substitutions(self, slug) -> SubstitutionsResponse
    def get_missing(self, slug, pantry_ingredient_ids) -> MissingResponse
    def get_regions(self) -> list[Region]

    # Community (uses internal_key)
    def submit_community(self, payload) -> SubmissionResponse
```

### Circuit breaker

State lives in Redis:
```
ffconsumer:engine:circuit_state       → "closed" | "open" | "half_open"
ffconsumer:engine:circuit_failures    → int (consecutive failures)
ffconsumer:engine:circuit_opened_at  → ISO timestamp
```

- Opens after 5 consecutive failures
- Half-open after 30 seconds
- On open: serve cached results + saved recipes, add `"engine_status": "degraded"` to response

### Resilience

| Rule | Detail |
|---|---|
| Timeout | 5 seconds per engine call |
| Retry | 1 retry on network error, no retry on 4xx |
| Circuit breaker | Open after 5 failures, half-open after 30 s |
| On 429 | Honour `Retry-After` header, surface to user |
| On engine down | Serve cache, add `engine_status: degraded` |

### Cache keys

```
ffconsumer:search:{sha256(sorted(ingredients) + mode + diet + dataset_version)}  TTL 5 min
ffconsumer:dish:{slug}:{dataset_version}                                           TTL 1 h
ffconsumer:ingredient_ac:{q}:{lang}                                                TTL 10 min
ffconsumer:engine:dataset_version                                                  TTL 1 h
ffconsumer:regions:{lang}                                                          TTL 24 h
```

Flush `ffconsumer:search:*` and `ffconsumer:dish:*` when `dataset_version` changes.

---

## 7. API Specification (v1)

### URL structure

```
/v1/                             — public API
/v1/auth/register                POST — create account
/v1/auth/login                   POST — email+password login
/v1/auth/otp/request             POST — request phone OTP
/v1/auth/otp/verify              POST — verify OTP, get tokens
/v1/auth/refresh                 POST — rotate JWT refresh token
/v1/auth/logout                  POST — revoke refresh token

/v1/me/profile                   GET, PATCH
/v1/me/diet                      GET, PATCH
/v1/me/export                    GET — user data export (GDPR-style)
/v1/me/devices                   GET, DELETE /<id>
DELETE /v1/me                    — soft delete account + grace period purge

/v1/pantry/                      GET, POST
/v1/pantry/<id>/                 DELETE

/v1/search/                      POST — wraps engine search with pantry + diet injection
/v1/resolve/                     POST — wraps engine ingredient resolve
/v1/ingredients/                 GET — autocomplete (cached)

/v1/dishes/<slug>/               GET — engine dish detail proxy + cache
/v1/dishes/<slug>/reviews/       GET, POST

/v1/saved/                       GET, POST
/v1/saved/<id>/                  PATCH, DELETE
/v1/collections/                 GET, POST
/v1/collections/<id>/            PATCH, DELETE
/v1/cooked/                      GET, POST

/v1/plans/<week>/                GET, PUT   (week = YYYY-Www)
/v1/plans/<id>/shopping-list/    POST — generate shopping list from plan
/v1/shopping-lists/<id>/         GET
/v1/shopping-lists/<id>/items/<item_id>/  PATCH — check/uncheck
/v1/shopping-lists/<id>/share/   GET — WhatsApp-ready text

/v1/budget/suggest/              POST — KES amount + servings + diet → engine search

/v1/regions/                     GET — proxies engine, cached 24h
/v1/stories/                     GET — editorial stories
/v1/stories/<slug>/              GET

/v1/submissions/                 GET (own), POST
/v1/submissions/<id>/            GET

/v1/plans/                       GET — billing plans (Free/Plus)
/v1/subscribe/                   POST — trigger M-Pesa STK push
/v1/subscription/                GET — current plan status
/v1/mpesa/callback/              POST — M-Pesa webhook (no auth, verified by signature)

/v1/devices/                     POST — register push token
/v1/sync/push/                   POST — offline sync: client pushes changes
/v1/sync/pull/                   GET  — offline sync: ?since=<ISO timestamp>

/v1/meta/version/                GET — backend + engine dataset_version
/v1/health/                      GET — health check (public, no auth)

/admin/                          Django admin (2FA mandatory, separate address in prod)
```

### API conventions

| Topic | Decision |
|---|---|
| Auth | JWT Bearer token in `Authorization` header; refresh token in `HttpOnly` cookie for web, body for mobile |
| Versioning | `/v1/` in path; additive only; 6-month deprecation notice |
| Pagination | Cursor-based with `limit` and `next` |
| Localisation | `lang=en\|sw` query param; falls back to English |
| Errors | One JSON shape: `{code, message, field_errors, request_id}` |
| Caching | ETag on dish detail; Redis for search, ingredients, regions |
| Docs | OpenAPI via drf-spectacular; TypeScript client (Orval/openapi-typescript); Kotlin client (openapi-generator) |
| Rate limits | Per-user and per-IP per endpoint; 429 with `Retry-After` |

### Public endpoints (no auth required)

- `GET /v1/health/`
- `GET /v1/meta/version/`
- `GET /v1/regions/`
- `GET /v1/stories/`, `GET /v1/stories/<slug>/`
- `GET /v1/dishes/<slug>/` (basic info, no personalisation)
- `POST /v1/mpesa/callback/` (verified by signature, not user auth)

---

## 8. Auth Architecture

### End users

| Flow | Detail |
|---|---|
| Email+password registration | Argon2id hash, breach check via HaveIBeenPwned API (k-anonymity) |
| Phone OTP | 6-digit code, 5-minute TTL, max 5 attempts before lockout |
| JWT access token | 15-minute TTL, signed HS256, carries `user_id` + `plan` |
| JWT refresh token | 30-day TTL, stored in DB for revocation, rotated on use |
| Device tokens | Every login creates a device record; remote logout revokes all tokens for a device |
| Optional 2FA | TOTP authenticator app for Plus users |

### Staff (admin)

| Detail | |
|---|---|
| Auth method | Django session + `django-two-factor-auth` |
| Required methods | TOTP authenticator app or hardware security key (passkey) |
| Prohibited | SMS codes, email codes — not allowed |
| Admin address | Separate path in dev, separate domain in prod |
| Step-up 2FA | Required for: account deletion, submission approve/reject, billing changes, role changes |
| Session rules | 15-min idle timeout, 8-hour max lifetime |

### Free vs Plus gating

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

Entitlement checks live in a single `entitlements.py` module checked by middleware and DRF permissions. They are never duplicated across views.

---

## 9. Payments (M-Pesa Daraja)

### Flow

```
1. User → POST /v1/subscribe/
2. Backend → Daraja STK Push API (initiates payment prompt)
3. User → confirms on phone
4. Daraja → POST /v1/mpesa/callback/ (unauthenticated, verified)
5. Backend:
   a. Verify source IP is in Safaricom's published IP range
   b. Verify callback signature (HMAC or Daraja-specific method)
   c. Re-check amount_kes == expected_amount (never trust callback amount alone)
   d. Check provider_ref is not already processed (idempotency)
   e. Update payment status to confirmed
   f. Activate Plus subscription
   g. Log audit_event
```

### Safety rules

- **Amount re-verification**: callback amount is cross-checked with the amount the user agreed to. Mismatch → reject.
- **Idempotent**: `provider_ref` is a unique key. Duplicate callbacks are silently ignored (HTTP 200 returned to Daraja).
- **Timeouts**: if confirmation does not arrive within 120 seconds, mark payment as failed; user can retry.
- **No card data**: never stored, never passed through the backend.
- **Sandbox**: `https://sandbox.safaricom.co.ke/` for staging.

---

## 10. Offline Sync (Android)

```
Android SQLite ◄──────────────────────────► Consumer Backend
  change_id (UUID)          POST /v1/sync/push/    server applies changes,
  changed_at (ISO)          array of changes        returns conflicts
  entity_type
  entity_id                 GET /v1/sync/pull/     server returns changes
  operation                 ?since=<ISO>           since last pull
  payload (JSON)
```

**Conflict rules:**
- Server wins for shared data (plan entries, shopping list items)
- User wins for pantry and personal notes
- Last-write-wins for profile fields
- `device.last_sync_at` updated on every successful pull

---

## 11. Safety Rules (non-negotiable)

1. **Diet/allergen always sent**: every engine search call includes `diet` populated from `profile_diet`. A user with allergen exclusions can never trigger an unfiltered search. This is enforced in `SearchService`, not in the view.
2. **Allergen text on every response** that mentions dietary info: *"Allergen information is for guidance only. Always confirm with the kitchen before ordering."*
3. **Engine never receives user data**: `user_id`, email, device token, subscription status — none of these go to the engine.
4. **Row-level scoping**: every queryset uses `filter(user=request.user)`. Automated tests try to access another user's data and must fail.
5. **M-Pesa amount re-check**: never activate Plus from the callback amount alone. Always re-verify against the expected amount stored at initiation.
6. **Ambiguous resolve → user choice, never a guess**: if the engine returns `status: ambiguous` for any token, return the choices to the client. Never pass an ambiguous token to search.

---

## 12. Security Architecture

### Defence in depth

```
1  EDGE         HTTPS only, Caddy WAF, DDoS protection, bot rules
2  GATEKEEPER   JWT auth, rate limits per user+IP, OTP throttling
3  APPLICATION  Input validation, explicit serialisers, row-level permissions,
                staff 2FA, CSRF, security headers
4  DATA          Private network, least-privilege DB user, field-level encryption
                for phone numbers, Argon2id passwords
5  OPERATIONS   Append-only audit log, external log store, alerts, backups,
                incident response
SUPPLY CHAIN   Pinned dependencies, pip-audit, secret scanning, SBOM,
                signed images, Actions pinned by commit, OIDC
```

### Threat model

| Asset | Threat | Main controls |
|---|---|---|
| User accounts + PII | Phishing, password reuse, SIM swap | Argon2id, OTP throttling, breach check, 2FA option, field encryption for phone |
| Pantry + meal plans | Cross-user access | Row-level scoping + permission tests in CI |
| Payment callbacks | Replay, wrong amount, forged callback | IP allowlist + signature + amount re-check + idempotency key |
| JWT tokens | Theft, replay | Short access TTL (15 min), DB-revocable refresh, HTTPS only |
| Engine API keys | Leakage in code | Secret manager only, never in repo, gitleaks on pre-commit + CI |
| Staff accounts | Takeover | Mandatory 2FA (no SMS), step-up checks, login alerts, session limits |
| Audit log | Tampering | Append-only in DB + shipped to external store immediately |
| User data | Export/deletion not working | Automated tests for export and deletion endpoints |

### 12.1 Identity and access for staff

| Actor | Auth | 2FA | Session |
|---|---|---|---|
| Curator/reviewer | Password + second factor | Required (authenticator app) | 30 min idle, 12 h max |
| Moderator | Password + second factor | Required | Same |
| Data lead | Password + security key recommended | Required | 30 min idle, 8 h |
| Admin | Password + hardware security key or passkey | Required, hardware-backed | 15 min idle, 8 h; step-up for sensitive acts |
| Engineer | GitHub 2FA + VPN for staging | Required | Per provider |
| CI/CD | OIDC short-lived token | Not applicable | Minutes |

### 12.2 API security rules

| Risk | Control |
|---|---|
| Broken object auth | Row-level scope + permission tests |
| Broken auth | Argon2id, OTP throttling, JWT short TTL, revocation |
| Excessive data exposure | Serialisers list allowed fields explicitly |
| Rate limiting | Per user, per IP, per endpoint; 429 with Retry-After |
| Mass assignment | Write serialisers accept only named fields |
| Injection | ORM only, no raw SQL from user input |
| CSRF | Django CSRF on admin; JWT for API (stateless) |
| Input limits | Max ingredients per search, string lengths, body size |

### 12.3 Secrets management

| Secret | Where | Rotation |
|---|---|---|
| Django `SECRET_KEY` | Secret manager, env var | Yearly |
| `DATABASE_URL` | Secret manager | 90 days |
| `REDIS_URL` | Secret manager | 90 days |
| `ENGINE_API_KEY` | Secret manager | 90 days (overlap) |
| `ENGINE_INTERNAL_KEY` | Secret manager | 90 days (overlap) |
| M-Pesa credentials | Secret manager | On change or suspicion |
| JWT signing secret | Secret manager | Yearly |
| Backup encryption key | Held by two owners, offline + vault | Yearly |

### 12.4 Data protection and privacy (Kenya DPA 2019)

- **Personal data**: user email, phone (field-level encrypted), IP addresses, payment records
- **Consent records**: stored per user; queryable; users can revoke
- **Data export** (`GET /v1/me/export`): returns all user data as JSON within 30 seconds or queued async
- **Account deletion** (`DELETE /v1/me`): soft delete immediately, Celery task purges after grace period (7 days default, configurable)
- **Retention**: request logs 90 days; audit logs 2 years; backups 35 days rolling; deleted accounts purged after grace period
- **Breach procedure**: notify the Office of the Data Protection Commissioner, generally within 72 hours (confirm requirements with a lawyer)

---

## 13. Infrastructure and Deployment

```
APP SERVER (Docker on Render or self-hosted)
  Django API (Gunicorn, 2+ workers)
  Celery worker
  Celery beat

DATA
  PostgreSQL 16 (managed, daily backup, own DB — never shared with engine)
  Redis 7 (cache, rate limits, queue)
  Object storage (if needed for avatars later)

ROUTING
  Caddy (TLS, routing, compression)

MONITORING
  Sentry, structured logs, uptime checks, dashboards
```

### Environments

| | Local | CI | Staging | Production |
|---|---|---|---|---|
| Purpose | Development | Automated tests | Mirror of prod | Real traffic |
| Data | Sample | Throw-away | Dataset copy | Real |
| Who deploys | Developer | Pipeline | Pipeline | Pipeline + approval |
| Access | Developer | Pipeline only | Team + VPN | Named individuals + VPN |
| M-Pesa | Mock | Mock | Sandbox | Live |

### Staging servers

Two staging targets:
1. **Render (Frankfurt)** — `render.yaml` driven, auto-deploy from `main`
2. **Self-hosted ThinkPad** (`mayday@100.96.139.83`) — same server as engine, path `/home/mayday/ff-consumer`

### Deployment strategy

- **Immutable artefacts**: one signed image per change, moves from staging → production unchanged
- **Zero-downtime**: two containers behind router; one replaced at a time after health check
- **Configuration**: injected from environment; no secrets in images
- **Rollback**: redeploy previous signed image (minutes)
- **Expand-only migrations**: backward-compatible changes applied first; breaking changes in two releases

### render.yaml (pattern)

```yaml
services:
  - type: web
    name: ff-consumer
    runtime: python
    region: frankfurt
    plan: free
    buildCommand: pip install -r requirements/prod.txt && python manage.py migrate --no-input && python manage.py collectstatic --no-input
    startCommand: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120
    healthCheckPath: /v1/health/
    envVars:
      - key: DJANGO_SETTINGS_MODULE
        value: config.settings.prod
      - key: SECRET_KEY
        generateValue: true
      - key: DATABASE_URL
        fromDatabase:
          name: flavorfind-consumer-db
          property: connectionString
      - key: ENGINE_BASE_URL
        value: https://engine.flavorfind.co.ke
      - key: ENGINE_API_KEY
        sync: false   # set manually in Render dashboard
      - key: ENGINE_INTERNAL_KEY
        sync: false   # set manually in Render dashboard

databases:
  - name: flavorfind-consumer-db
    databaseName: flavorfind_consumer_db
    plan: free
    region: frankfurt
```

---

## 14. Repository and Governance

Mirrors the engine's setup exactly. See `engine-reference.md` for full detail.

### Key files

| File | Purpose |
|---|---|
| `README.md` | What the backend is, how to run, how to test, where docs live |
| `CODEOWNERS` | `accounts/`, `billing/`, `engine_client/` owned by security reviewer |
| `.pre-commit-config.yaml` | ruff, gitleaks, private-key detection, large-file check |
| `.github/workflows/ci.yml` | PR pipeline |
| `.github/workflows/main.yml` | Build + deploy to staging |
| `.github/workflows/release.yml` | Production deploy |
| `.github/workflows/nightly.yml` | Fuzzing, DAST, scans |
| `.github/workflows/weekly.yml` | Load test, restore drill, access review |
| `pyproject.toml` | ruff, mypy, pytest, coverage config |
| `Makefile` | `up`, `down`, `test`, `test-cov`, `lint`, `format`, `typecheck`, `migrate`, `shell` |
| `render.yaml` | Render deployment |
| `docker-compose.yml` | Local dev: web + db + redis + worker |

### Branch protection (main)

- PR required (no direct push, including owners)
- 1 approval; 2 when team exceeds 3 developers
- Code owner review for `accounts/`, `billing/`, `engine_client/`, workflow files
- All CI jobs must pass
- Signed commits required
- Squash merge only
- No bypass for anyone

---

## 15. Continuous Integration (CI) Pipelines

### PR pipeline (target: under 10 minutes)

| Job | Tools | Fails when |
|---|---|---|
| Lint + format | ruff | Any violation |
| Type check | mypy | Any error in `accounts`, `billing`, `engine_client` |
| Secret scan | gitleaks | Any secret found |
| SAST | bandit, semgrep | High severity finding |
| Dependency audit | pip-audit | High/critical with a fix |
| Unit tests | pytest + real Postgres + Redis containers | Any failure |
| Coverage gate | coverage | Below 85% overall or 95% for `accounts`/`billing`/`engine_client` |
| Migration check | Django | Missing migration; build-from-empty fails; latest migration non-reversible |
| Permission tests | pytest | Any user accesses another user's data |
| Safety golden set | pytest | Any vegetarian-with-meat, any allergen-in-result case |
| Engine contract | oasdiff, Schemathesis | Breaking engine OpenAPI change |
| Build image | Docker | Build failure |
| Image scan | Trivy | High/critical with a fix |
| SBOM | CycloneDX or Syft | Not blocking; stored with release |
| Config lint | hadolint, yamllint, actionlint | Any error |

### Main pipeline (after merge, target: under 15 minutes)

1. Re-run full test suite (confirms main is green)
2. Build image once (same image goes to staging and production)
3. Tag with commit ID (immutable)
4. Push to private registry
5. Sign image and attach provenance
6. Deploy to staging (Render + self-hosted)
7. Smoke tests: health, register, login, search, save, GET /v1/meta/version/
8. Short performance check: 2-minute load test; fail if p95 > 20% worse than baseline
9. Publish OpenAPI docs
10. Notify team channel

### Release pipeline (to production)

1. Verify signed tag from an authorised release manager
2. Verify image digest matches the one that passed staging
3. Approval gate (second person, not the tagger)
4. Pre-deploy backup
5. Expand-only migrations
6. Rolling deploy
7. Health gate (auto-rollback on failure)
8. Smoke tests against production with test credentials
9. Release records (GitHub release, Sentry release marker, changelog)
10. 30-minute watch window

### Nightly

- Full golden set with extended fuzzing
- Dependency advisories re-check
- Base image rebuild and scan
- OWASP ZAP DAST baseline scan against staging
- Backup integrity check

### Weekly

- Full load test against staging (search p95 < 250 ms at 50 req/s)
- Restore drill: restore staging DB from latest backup, verify data integrity
- Access review report

### Quality gates summary

| Gate | Threshold |
|---|---|
| Coverage | 85% overall; 95% for `accounts`, `billing`, `engine_client` |
| Permission tests | Zero cross-user access |
| Safety golden set | 100% on diet/allergen cases |
| Vulnerabilities | No unresolved high/critical with a fix |
| Secrets | Zero detected |
| Performance | Search p95 < 250 ms; within 20% of baseline |
| API compatibility | No breaking change in v1 |
| Pipeline speed | PR pipeline under 10 minutes |

---

## 16. Testing Architecture

| Layer | What it checks | Tools |
|---|---|---|
| Unit | Services, budget logic, entitlements, OTP, payment idempotency | pytest |
| Property-based | Sync is idempotent; plan never loses entries; entitlement never grants Plus without payment; allergen exclusion always wins | Hypothesis |
| Permission tests | No user can read or change another user's data | pytest |
| Safety golden set (~40 cases) | Vegetarian profile never returns meat; excluded allergen never appears; Swahili input resolves; explore mode labels missing items; "unga" asks, never guesses | pytest |
| Engine contract | Generated client compiles; ambiguity, zero-result, 429, engine-down paths tested | pytest + Schemathesis |
| Payments | Duplicate callback, timeout, wrong amount, expired subscription, successful activation | pytest + mock Daraja |
| Performance | Search p95 < 250 ms at 50 req/s; query-count budgets (no N+1) | Locust |
| Offline sync | Android sync replay with conflicting edits, last-write-wins, no data loss | pytest |

### Safety golden set structure

| Category | Cases | What it protects |
|---|---|---|
| Allergen exclusion | 10 | Excluded allergen never appears in results, regardless of score |
| Vegetarian | 5 | Vegetarian profile never returns meat, fish, or poultry dishes |
| Diet tags | 5 | Other diet tags (halal, gluten-free, nut-free) correctly filtered |
| Ambiguity | 5 | "unga", "pepper" return choices, never a guess |
| Swahili input | 5 | nyanya→tomato, sukuma→sukuma wiki, etc. |
| Explore mode | 5 | Missing items named and labelled; not shown in strict mode |
| Allergen text | 5 | Every dietary response includes the standard allergen disclaimer |
| Total | ~40 | |

---

## 17. Observability and Operations

| Area | Plan |
|---|---|
| Error tracking | Sentry with release markers and request IDs |
| Metrics | Request rate, latency (p50, p95, p99), error rate, cache hit rate, payment confirmation rate, engine call health, signup rate, DAU, search per user, zero-result rate |
| Logs | Structured JSON, request IDs, no secrets, 90-day retention |
| Uptime | External checks every minute on `/v1/health/` and a real search |
| Dashboards | Service health, engine call health, payment funnel, cache metrics, security events |
| Status page | Public, once live |

### Service level objectives

| Objective | Target |
|---|---|
| Availability | 99.5% per month |
| Search p95 | < 250 ms |
| Error rate | < 0.5% |
| Payment confirmation | < 30 seconds for 95% |
| Recovery | RPO 1 hour, RTO 4 hours |
| SEV1 response | 15 minutes |
| SEV2 response | 1 hour |

### Operating rhythm

| When | Activity |
|---|---|
| Daily | Check dashboards and alerts; review zero-result list |
| Weekly | Dependency updates, restore drill result, access report |
| Every iteration | Demo, retrospective, security checklist review |
| Quarterly | Access review, secret rotation check, disaster drill |

### Runbooks to write (in `docs/runbooks/`)

- Deploy and roll back
- Restore from backup
- Rotate a secret or API key
- Revoke a JWT token or device
- Add a staff user (with 2FA enrolment)
- Reset 2FA after verification
- Respond to M-Pesa callback failure
- Respond to engine outage (degraded mode)
- Handle account deletion request
- Incident response (per alert type)

---

## 18. Full Iteration Plan

Five two-week iterations (~10 weeks). Every iteration ships to staging. Every iteration has four lanes moving together.

---

### Iteration 1 — Foundations (Weeks 1–2)

**Goal:** Django project up, users can register/login, engine client works, first engine call visible in staging.

#### Engine development lane

- [ ] Repo from engine template: `apps/`, `config/`, `requirements/`, `docker/`, `docs/`
- [ ] `core` app: `TimeStampedModel`, request ID middleware, error format, custom exception handler, pagination
- [ ] `accounts` app: `CustomUser`, registration (email+password), login, JWT access + refresh tokens, logout, device registration
- [ ] Phone OTP: request + verify endpoints, 6-digit code, 5-minute TTL, max 5 attempts
- [ ] `profiles` app: `Profile`, `ProfileDiet` — `PATCH /v1/me/profile`, `PATCH /v1/me/diet`
- [ ] `engine_client` app: typed client, `ENGINE_BASE_URL` + `ENGINE_API_KEY` from settings, health ping, version fetch, circuit breaker skeleton, cache layer
- [ ] `api` app: URL router `/v1/`, OpenAPI schema via drf-spectacular, `GET /v1/health/`, `GET /v1/meta/version/`
- [ ] Settings: base, dev, test, prod (same pattern as engine)
- [ ] `docker-compose.yml`: web + db + redis + worker
- [ ] `Makefile`, `pyproject.toml` tooling

#### DevOps and security lane

- [ ] GitHub org: branch protection, CODEOWNERS, templates (reuse from ff-engine)
- [ ] Pre-commit hooks: ruff, gitleaks, mypy
- [ ] CI skeleton: lint, SAST (bandit), pip-audit, pytest, migration check, schema validation
- [ ] Staging on Render: free tier, Frankfurt, PostgreSQL + Redis
- [ ] Staff 2FA enforced (`django-two-factor-auth`)
- [ ] Admin on separate path, blocked from public in prod
- [ ] Secret manager for `ENGINE_API_KEY` and `ENGINE_INTERNAL_KEY`

#### Data / content lane

- [ ] Seed `plan` table with Free and Plus plan records
- [ ] Agree `diet_tag_slug` values to use (must match engine dietary tag slugs)

#### Demo and exit check

- [ ] Register a user → log in → set a diet → call `GET /v1/meta/version/` → see `dataset_version` in response
- [ ] First rollback practised: deploy a broken build, auto-rollback triggers

---

### Iteration 2 — Search and Pantry (Weeks 3–4)

**Goal:** Core product works. User with a pantry can search for what to cook.

#### Engine development lane

- [ ] `pantry` app: `GET`, `POST`, `DELETE /v1/pantry/<id>/`
- [ ] Engine client: `resolve()`, `search()`, `get_pairings()`, `get_substitutions()`, `get_missing()`, `get_ingredients()` (autocomplete)
- [ ] Ambiguity flow: when resolve returns `ambiguous`, return choices to client
- [ ] `POST /v1/resolve/` — wraps engine resolve
- [ ] `POST /v1/search/` — wraps engine search, injects pantry items + profile diet, personalisation layer
- [ ] `GET /v1/ingredients/` — autocomplete (cached, debounced)
- [ ] `GET /v1/dishes/<slug>/` — proxy engine dish detail + cache with ETag
- [ ] Engine cache: Redis keyed by `sha256(inputs + diet + dataset_version)`
- [ ] Circuit breaker: open after 5 failures, half-open after 30 s; degraded mode response
- [ ] Safety golden set: first ~20 allergen/diet cases in CI

#### DevOps and security lane

- [ ] Full PR pipeline running (all CI jobs from section 15)
- [ ] Engine contract job: runs against engine staging, fails on breaking OpenAPI change
- [ ] Rate limits per user + per IP per endpoint
- [ ] Permission tests: user A cannot see user B's pantry

#### Demo and exit check

- [ ] Pantry search returns exact/can_make/almost tiers with explained reasons
- [ ] "unga" triggers choice picker, not a guess
- [ ] Vegetarian profile never returns meat dishes
- [ ] Excluded allergen never appears in results
- [ ] Engine-down: fallback returns cached results + `engine_status: degraded`

---

### Iteration 3 — Library, Planner, Offline (Weeks 5–6)

**Goal:** Users can save recipes, plan a week, generate a shopping list, and sync offline.

#### Engine development lane

- [ ] `library` app: `SavedRecipe`, `Collection`, `CookLog` — CRUD + `POST /v1/cooked/`
- [ ] `planner` app: `MealPlan`, `MealPlanEntry`, `ShoppingList`, `ShoppingItem`
  - `GET/PUT /v1/plans/<week>/`
  - `POST /v1/plans/<id>/shopping-list/`
  - `GET /v1/shopping-lists/<id>/share/` — returns WhatsApp-ready text
- [ ] `budget` app: `POST /v1/budget/suggest/` — KES + servings + diet → engine search with cost filter
- [ ] `content` app: `Story` model, `GET /v1/regions/` (proxies engine), `GET /v1/stories/`, `GET /v1/stories/<slug>/`
- [ ] `sync` app: `POST /v1/sync/push/`, `GET /v1/sync/pull?since=`
- [ ] Dataset drift check: Celery beat task, nightly, calls engine `/v1/datasets/?since=<version>`, flags changed/removed saved recipes
- [ ] Audit log: append-only `AuditEvent`, shipped to external log store via Celery task

#### DevOps and security lane

- [ ] Audit log wired and shipping
- [ ] Nightly DAST + fuzzing added to CI
- [ ] OpenAPI docs complete; TypeScript client generated; Kotlin client generated

#### Demo and exit check

- [ ] Plan a full week → generate a shopping list → check item off → share WhatsApp text
- [ ] Edit pantry on two "devices" (two API tokens) → sync without data loss
- [ ] At least 3 region stories visible via API (`GET /v1/stories/`)

---

### Iteration 4 — Community, Money, Notifications (Weeks 7–8)

**Goal:** Users can submit recipes, pay for Plus, and receive notifications.

#### Engine development lane

- [ ] `community` app:
  - `POST /v1/submissions/` — draft, validates required fields, queues for moderation
  - `GET /v1/submissions/` — user's own with status
  - `POST /v1/dishes/<slug>/reviews/` — rating + text, queued for moderation
  - Celery worker: on moderation approval, forwards to engine `POST /v1/internal/submissions/` using `ENGINE_INTERNAL_KEY`
- [ ] `billing` app:
  - `GET /v1/plans/` — Free and Plus plan details
  - `POST /v1/subscribe/` — triggers M-Pesa STK push
  - `POST /v1/mpesa/callback/` — verifies signature, confirms payment, activates Plus
  - `GET /v1/subscription/` — current plan, renews_at, trial status
  - Entitlement checks on gated endpoints (meal plans, nutrition, offline sync)
  - Celery beat: renewal reminders, expiry checks
- [ ] `notifications` app: push token registration, in-app table, preference CRUD
- [ ] `partners` app: sponsored slot model
- [ ] `moderation` app: admin queue for submissions and reviews, audit trail

#### DevOps and security lane

- [ ] M-Pesa callback: source IP validation + signature verification in CI
- [ ] Payment tests: duplicate callback, wrong amount, expired sub, timeout
- [ ] Step-up 2FA for staff: moderation approve/reject requires re-auth
- [ ] `GET /v1/me/export` — user data as JSON
- [ ] `DELETE /v1/me` — soft delete + grace period purge via Celery
- [ ] Consent records stored and queryable
- [ ] Threat model review (document in `docs/threat-model.md`)

#### Demo and exit check

- [ ] Pay with M-Pesa sandbox → Plus activates → meal plans and nutrition unlock
- [ ] Submit a recipe → appears in moderation queue → approve → Celery forwards to engine
- [ ] `DELETE /me` → data purged after grace period → audit event logged

---

### Iteration 5 — Hardening and Release (Weeks 9–10)

**Goal:** v1.0.0 — production-ready, app teams integrated.

#### Engine development lane

- [ ] Bug fixes from iterations 1–4
- [ ] Performance tuning: query count budgets, N+1 fixes
- [ ] Final API freeze: no breaking changes after this point for v1
- [ ] App team integration support (website + Android consuming generated clients)

#### DevOps and security lane

- [ ] Load test: search p95 < 250 ms at 50 req/s on staging
- [ ] Soak test: 2-hour sustained load
- [ ] External penetration test — fix all high/critical findings
- [ ] Backup restore drill: restore staging DB from backup, verify data integrity
- [ ] Rollback drill: deploy v1.0.0-rc1, roll back to previous, verify health
- [ ] Incident tabletop: simulate engine outage, payment callback failure
- [ ] Security go-live checklist signed

#### Demo and exit check

- [ ] All exit criteria in section 19 met
- [ ] Website and Android teams integrated using generated clients
- [ ] v1.0.0 tagged and live

---

## 19. Exit Criteria for Consumer Backend v1.0

| Area | Criterion | Evidence |
|---|---|---|
| Engine integration | All engine endpoints used correctly; contract job green; ambiguity, 429, outage paths proven | CI report + manual test |
| Safety | Safety golden set at 100%: vegetarian/allergen cases pass; zero unfiltered searches for profiles with exclusions | CI golden set report |
| Product | Search, pantry, saved, planner, shopping, budget, community, Plus billing, offline sync — all E2E | Demo recording |
| Quality | Coverage gates met (85% overall, 95% accounts/billing/engine_client); property + permission tests green | CI coverage report |
| Performance | Search p95 < 250 ms at 50 req/s on staging | Load test report |
| Security | 2FA on every staff account; no open high/critical; pen test findings fixed; go-live checklist signed | Checklist + scan report |
| Privacy | Consent, export, deletion, privacy notice, breach procedure in place | Documents + endpoint tests |
| Ops | Signed images only; rollback + restore drills passed; dashboards + alerts live; runbooks complete | Drill records |
| API docs | OpenAPI complete; TypeScript client compiles; Kotlin client compiles; app teams integrate in under a day | Integration demo |

### Security go-live checklist

| Item | Evidence |
|---|---|
| 2FA enforced on every staff account | User report + screenshots |
| Branch protection + signed commits with no bypass | Settings export |
| All pipelines green; no open high/critical vulnerabilities | CI + scan reports |
| `ENGINE_API_KEY` and `ENGINE_INTERNAL_KEY` in secret manager; not in code | gitleaks report |
| DB and Redis not reachable from the internet | Port scan |
| Rate limits, OTP throttling, JWT revocation tested | Test report |
| Backups encrypted, off-site, restore drilled | Drill record |
| M-Pesa callback: IP check + signature + amount re-verify | Test report |
| Permission tests: cross-user access fails | CI report |
| Allergen/diet safety golden set at 100% | CI report |
| Pen test findings fixed or formally accepted | Test report + fix list |
| Incident playbooks written + tabletop held | Playbooks + notes |
| Audit log shipping to external store verified | Sample records |
| Privacy notice + consent + export + deletion working | Documents + endpoint tests |

---

## 20. Team and Responsibilities

| Role | Responsibilities | Time |
|---|---|---|
| Product owner | Priorities, billing decisions, content approval | Part-time |
| Tech lead / backend developer | Architecture, backend code, release manager | Full-time |
| Second developer | Features, tests, generated clients | Full-time |
| DevOps (tech lead initially) | Pipelines, infra, access, monitoring | ~30% initially |
| Content lead | Taste of 47 counties stories | Part-time |
| Security advisor | Threat model, pen test | Short engagements |

### Who decides what (R = does it, A = accountable, C = consulted, I = informed)

| Activity | Product owner | Tech lead | DevOps |
|---|---|---|---|
| Deploy to production | I | A | R |
| Create or revoke API key | I | C | A+R |
| Activate or cancel a subscription (manual) | A | C | R |
| Approve moderation action | A | I | I |
| Respond to security incident | I | R | A |
| Rotate secrets | I | A | R |
| Quarterly access review | I | C | A+R |

---

## 21. Risks and Open Decisions

| Risk | Mitigation |
|---|---|
| M-Pesa sandbox behaves differently from live | Test every edge case (duplicate, timeout, wrong amount) in sandbox before launch; document differences |
| Diet/allergen bug ships to production | Safety golden set in CI; must be 100% before any merge to main |
| Engine API changes break the client | Engine contract job in CI (oasdiff); engine v1 is additive-only; client ignores unknown fields |
| Cross-user data leak | Row-level scoping enforced; automated permission tests in CI |
| JWT token stolen | Short TTL (15 min); HTTPS only; refresh token DB-revocable; device list in settings |
| Plus entitlement bypass | Single `entitlements.py` module; automated tests verify gating works; never trust client claims |
| Account deletion not working | Automated test for `DELETE /me`; Celery task monitored; purge verified in drill |
| Offline sync data loss | Property tests: sync must be idempotent; conflict rules documented + tested |
| Engine outage | Circuit breaker tested; degraded mode demo in Iteration 2 exit check |

### Decisions still open (resolve before Iteration 4)

- Plus trial length: 14 days or 30 days?
- Moderation staffing: who reviews submissions? what is the turnaround SLA?
- Taste of 47 counties: who writes the stories? which 5–10 counties launch first?
- Minimum Android app version to support at launch

---

*Next step: create `ff-consumer` repository from the engine template, start Iteration 1 with the parallel tracks: developer sets up skeleton while content team begins writing stories.*
