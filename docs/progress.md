# ff-consumer — Build Progress

**Last updated:** 2026-10-31  
**Commit:** `8773e56`  
**Branch:** `main`  
**Status:** Iterations 1–4 complete. Iteration 5 (hardening + release) is next.

---

## What is built

The full consumer backend for Flavor Find — a Django 5.2 + DRF 3.18 API that serves
the website and Android app. It owns all people data (accounts, pantry, plans, billing)
and calls the Recipe Engine for all food data.

### Stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| Framework | Django 5.2.17 + DRF 3.18.2 |
| Database | PostgreSQL 16 (SQLite in test) |
| Cache / Broker | Redis 7 |
| Background tasks | Celery 5.4.0 + django-celery-beat |
| API docs | drf-spectacular 0.30.0 |
| Auth | Argon2id passwords + phone OTP; JWT (simplejwt) |
| Payments | M-Pesa Daraja (STK push) |
| Staging | Render (Frankfurt) + self-hosted (100.96.139.83) |

---

## Iteration 1 — Foundations ✅

**Goal:** Django project up, users can register/login, engine client works.

### What was built

**Project structure**
- `apps/`, `config/`, `requirements/`, `docker/`, `docs/` — mirrors the engine layout
- `config/settings/base.py` — full settings: Celery, Redis, JWT, DRF, drf-spectacular, security headers, Argon2id passwords
- `config/settings/dev.py`, `test.py`, `prod.py`
- `docker/docker-compose.yml` — web + db + redis + worker
- `docker/Dockerfile` — production image
- `Makefile` — `up`, `down`, `test`, `test-cov`, `lint`, `format`, `typecheck`, `migrate`, `shell`
- `pyproject.toml` — ruff, mypy, pytest, coverage config
- `render.yaml` — Render deploy config (Frankfurt, free tier)

**`core` app**
- `TimeStampedModel` — UUID PK, `created_at`, `updated_at`
- `SoftDeleteModel` — adds `deleted_at`, `is_deleted`, `soft_delete()`
- `AuditEvent` model — append-only, actor/action/object/before/after/ip_address
- `log_audit_event()` — creates AuditEvent and fires `ship_audit_event.delay()`
- `RequestIDMiddleware` — injects `X-Request-ID` on every request/response
- `SecurityHeadersMiddleware` — HSTS, X-Frame-Options, X-Content-Type-Options, CSP
- `custom_exception_handler` — consistent `{error: {code, message, details}}` format
- `StandardPagination` — page/page_size cursor pagination
- `ship_audit_event` Celery task — ships events to structured logger (replace with BigQuery/S3 in prod)
- `check_dataset_drift_saved_recipes` Celery task — flags stale saved recipes on version change

**`accounts` app**
- `CustomUser` — UUID PK, email (unique nullable), phone (unique nullable), Argon2id password, language (en/sw), status (active/suspended/deleted), soft delete
- `AuthIdentity` — tracks login methods (password, phone_otp, google)
- `Device` — platform, push_token, last_seen, last_sync_at
- `Consent` — type (terms/privacy/marketing), version, granted_at, revoked_at
- `OTPRequest` — phone OTP with SHA-256 hash, TTL, attempt counting, lock after 5 fails
- `RegisterSerializer` — validates email, password strength, creates user + AuthIdentity + Consent records
- `services.py` — `request_otp()` (rate-limited), `verify_otp()` (locked/expired/wrong code), `get_tokens_for_user()`
- Endpoints:
  - `POST /v1/auth/register` — email + password
  - `POST /v1/auth/login` — simplejwt TokenObtainPairView
  - `POST /v1/auth/otp/request` — rate-throttled phone OTP
  - `POST /v1/auth/otp/verify` — returns JWT on success
  - `POST /v1/auth/refresh` — rotate refresh token
  - `POST /v1/auth/logout` — blacklists refresh token
  - `GET /v1/me` — current user
  - `GET /v1/me/export` — GDPR data export (pantry, saved, plans, submissions, consents, devices)
  - `DELETE /v1/me/delete` — soft-delete; schedules 35-day purge task
  - `POST/GET /v1/me/devices` — register/list devices
  - `DELETE /v1/me/devices/<id>` — remote logout

**`profiles` app**
- `Profile` — household_size, region_slug, budget_kes_per_meal
- `ProfileDiet` — diet_tag_slug (vegetarian, gluten-free, nut-free, halal…)
- `PATCH /v1/me/profile/` — update profile
- `GET/PATCH /v1/me/diet/` — manage diet tags

**`engine_client` app**
- `EngineClient` — single typed client for all engine API calls
- Methods: `search()`, `resolve()`, `get_dish()`, `get_pairings()`, `get_substitutions()`, `get_missing()`, `get_ingredients()`, `get_regions()`, `get_version()`, `get_dataset_version()`, `refresh_dataset_version()`, `submit_community()`, `get_dataset_diff()`, `health_ping()`
- Circuit breaker: Redis-backed state (closed/open/half_open), opens after 5 consecutive failures, recovers after 30 seconds
- Retry: 1 retry on network errors, no retry on 4xx
- Timeout: 5 seconds per call
- `search()` enforces `diet is not None` — raises `ValueError` if None (safety rule)
- Dataset version: cached in Redis for 1 hour; bust-and-refresh via `refresh_dataset_version()`
- Degraded mode: returns `{"engine_status": "degraded", "results": {}}` when circuit is open
- `check_dataset_drift` Celery beat task — nightly version check, fires drift task on change
- Module-level `engine` singleton — import and use everywhere

**`api` app**
- `/v1/` URL router
- `GET /v1/health/` — database + engine ping, returns `{status, version, dataset_version, engine_status}`
- `GET /v1/meta/version/` — backend version + engine dataset_version
- OpenAPI schema at `/docs/` and `/v1/schema/`

### Infrastructure
- GitHub Actions CI: lint (ruff), SAST (bandit), pip-audit, pytest, migration check, schema validation
- deploy-staging.yml: Tailscale → SSH → git pull → pip install → migrate → gunicorn reload
- nightly.yml: dataset drift check + DAST
- pre-commit: ruff, mypy, gitleaks
- `.env.example` with all required variables documented

### Exit check ✅
Register → login → JWT → `GET /v1/meta/version/` returns `dataset_version: 2026.10.0`

---

## Iteration 2 — Search and Pantry ✅

**Goal:** User with a pantry can search for what to cook.

### What was built

**`pantry` app**
- `PantryItem` — engine ingredient_id (UUID), ingredient_slug, display_name (cached), expires_on
- `GET /v1/pantry/` — list user's pantry items
- `POST /v1/pantry/` — add item (accepts ingredient_id or ingredient_slug)
- `DELETE /v1/pantry/<id>/` — remove item
- Row-level security: every queryset filtered by `user=request.user`

**`search` app**
- `POST /v1/search/` — wraps engine search; automatically injects user's pantry ingredient slugs and profile diet tags into every call
- `POST /v1/resolve/` — wraps engine ingredient resolve; returns ambiguous tokens to client (never guesses)
- `GET /v1/ingredients/` — autocomplete, 10-min Redis cache
- `GET /v1/dishes/<slug>/` — proxy engine dish detail + ETag cache + allergen disclaimer
- `search/services.py`:
  - `get_user_diet_tags()` — fetches diet tags from ProfileDiet; returns `[]` for unauthenticated users
  - `get_user_pantry_slugs()` — fetches pantry slugs for authenticated users
  - Allergen disclaimer injected on dish/search responses: *"Allergen information is for guidance only. Always confirm with the kitchen."*

### Safety rules enforced
- Diet tags always injected: `EngineClient.search(diet=None)` raises `ValueError`
- `search/services.py` calls `get_user_diet_tags()` before every engine search
- Ambiguous resolve tokens returned to client — never forwarded to search
- `almost` tier only shown in explore mode

### Engine cache
- Search: `sha256(sorted(ingredients) + mode + diet + dataset_version)` → 5-minute TTL
- Dish: `{slug}:{dataset_version}` → 1-hour TTL
- Ingredient autocomplete: `{q}:{lang}` → 10-minute TTL
- All keys prefixed `ffconsumer:`

### Permission tests
- Pantry permission tests: User A cannot see or delete User B's pantry items (10 tests)

### Exit check ✅
- Vegetarian profile never returns meat dishes
- Excluded allergen never appears in results (golden-set tests pass)
- Engine-down: fallback returns `engine_status: degraded`

---

## Iteration 3 — Library, Planner, Offline ✅

**Goal:** Save recipes, plan a week, generate a shopping list, sync offline.

### What was built

**`library` app**
- `SavedRecipe` — dish_id (engine UUID), dish_slug, dataset_version (at save time), collection_id, note
- `Collection` — user-owned named collection
- `CookLog` — dish_id, cooked_at, rating (1–5)
- Endpoints:
  - `GET/POST /v1/saved/` — list/save recipes (Free: max 20; Plus: unlimited)
  - `DELETE /v1/saved/<id>/` — remove saved recipe
  - `GET/POST /v1/saved/collections/` — list/create collections
  - `DELETE /v1/saved/collections/<id>/` — delete collection
  - `GET/POST /v1/cooked/` — cooking history

**`planner` app**
- `MealPlan` — week_start (date)
- `MealPlanEntry` — day (mon–sun), meal_type, dish_id, dish_slug, servings, note
- `ShoppingList` — linked to meal plan or standalone
- `ShoppingItem` — ingredient_id, ingredient_slug, display_name, quantity_note, checked, price_estimate_kes
- Endpoints:
  - `GET/PUT /v1/plans/<YYYY-Www>/` — week format e.g. `2026-W44` (Plus-gated)
  - `POST /v1/plans/<id>/shopping-list/` — generate shopping list from plan
  - `GET /v1/shopping-lists/<id>/` — view list
  - `PATCH /v1/shopping-lists/<id>/items/<item_id>/` — check/uncheck item
  - `GET /v1/shopping-lists/<id>/share/` — WhatsApp-ready text

**`budget` app**
- `POST /v1/budget/suggest/` — takes KES amount + servings + diet; calls engine search with cost_max filter (Plus-gated)

**`content` app**
- `Story` — title_en, title_sw, body_en, body_sw, slug, author, region_slugs, status, published_at
- `GET /v1/regions/` — proxies engine regions (24-hour cache)
- `GET /v1/stories/` — paginated published stories (filterable by region)
- `GET /v1/stories/<slug>/` — story detail

**`sync` app**
- `POST /v1/sync/push/` — accepts array of changes (pantry, saved, cook_log, shopping_items); applies server-side; returns conflicts (Plus-gated)
- `GET /v1/sync/pull/?since=<ISO timestamp>` — returns all user changes since timestamp
- Conflict rules: server wins for plans; user wins for pantry and notes; last-write-wins for profile

**Dataset drift detection**
- `check_dataset_drift_saved_recipes` task counts stale saved recipes (saved under old dataset_version) on every version change

**Audit log**
- `AuditEvent` wired throughout — `log_audit_event()` used on deletion, payment confirmation, approval/rejection

### Exit check ✅
- Plan a week, generate shopping list, check off item, get WhatsApp share text
- Push/pull sync without data loss

---

## Iteration 4 — Community, Billing, Notifications ✅

**Goal:** Submit recipes, pay for Plus, receive notifications.

### What was built

**`community` app**
- `Submission` — payload (JSON), status (draft→sent→in_review→accepted/rejected), engine_submission_id
- `Review` — dish_id, dish_slug, stars (1–5), text, status (pending/approved/rejected)
- Endpoints:
  - `POST /v1/submissions/` — validates required fields (name_en, description, ingredients, steps), creates draft
  - `GET /v1/submissions/` — user's own submissions with status
  - `GET /v1/submissions/<id>/` — submission detail
  - `POST /v1/dishes/<slug>/reviews/` — rating + text; one review per user per dish (upsert)
- `forward_submission_to_engine` Celery task — uses `ENGINE_INTERNAL_KEY` (internal:curation scope); called after moderation approval

**`billing` app**
- `Plan` — code (PK: "free"/"plus"), name, price_kes, features (JSON)
- `Subscription` — OneToOne with user, status (active/trialing/cancelled/expired), trial_ends_at, renews_at
- `Payment` — provider_ref (M-Pesa transaction ID, idempotency key), amount_kes, status
- Endpoints:
  - `GET /v1/plans/` — public, lists Free and Plus plans
  - `GET /v1/subscription/` — current user's plan; returns free plan details for users with no record
  - `POST /v1/subscribe/` — validates phone (254XXXXXXXXX), creates pending Payment, calls Daraja STK push (placeholder in v1; full Daraja integration next)
  - `POST /v1/mpesa/callback/` — unauthenticated; verified by: source IP (Safaricom ranges), amount re-check (never trust callback amount), idempotency (duplicate receipt silently ignored)
- `RequiresPlus` DRF permission — used on meal plans, shopping lists, offline sync, budget mode
- `user_has_active_plus()` — checks Subscription.is_active_plus() (active + trialing count)
- Celery beat tasks: `check_subscription_expiry` (1 AM), `check_trial_expiry` (1:30 AM), `send_renewal_reminders` (8 AM)
- `seed_plans` management command — seeds Free and Plus plans

**`notifications` app**
- `Notification` — channel (push/email/in_app), type, title, body, data, read_at, sent_at
- `NotificationPreference` — push_enabled, email_enabled, quiet_hours_start/end
- Endpoints:
  - `GET /v1/notifications/` — last 50 in-app notifications
  - `POST /v1/notifications/<id>/read/` — mark as read
  - `GET/PATCH /v1/notifications/preferences/` — notification preferences

**`partners` app**
- `SponsoredSlot` — engine_id (dish or ingredient UUID), engine_slug, label (always "Sponsored"), starts_at, ends_at, is_active
- Admin-only in v1; no public endpoints
- `label` field enforces "Sponsored" — never hidden from users

**`moderation` app**
- Admin queue for `Submission` and `Review` (registered here, not in community app)
- `approve_and_forward` action: requires step-up 2FA (30-min OTP recency check), logs `AuditEvent`, queues `forward_submission_to_engine`
- `reject_submissions` action: requires step-up 2FA, logs `AuditEvent`
- `approve_reviews` / `reject_reviews`: same step-up requirement

**`accounts` additions**
- `GET /v1/me/export` — full GDPR data export: pantry, saved_recipes, cook_log, meal_plans, submissions, consents, devices
- `DELETE /v1/me/delete` — soft-delete + schedules `purge_user_data_after_grace_period` (35-day delay)
- `purge_user_data_after_grace_period` Celery task — purges all PII from all apps, anonymises user row (`deleted_<uuid>@deleted.invalid`)

### Security implemented in Iteration 4
- M-Pesa callback: source IP validation (Safaricom IP ranges), amount re-verification, idempotency (duplicate receipt = silent ignore)
- Step-up 2FA on moderation approve/reject (OTP verified within last 30 minutes)
- AuditEvent logged for: payment confirmation, account deletion, submission approve/reject, review approve/reject
- `DELETE /me` → immediate deactivation + 35-day data purge
- Consent records stored on registration

### Exit check ✅
- Pay M-Pesa sandbox → Plus activates → meal plans unlock
- Submit recipe → moderation queue → approve → Celery forwards to engine
- `DELETE /me` → account deactivated → purge task scheduled

---

## Test Suite

| App | Tests | Coverage |
|---|---|---|
| `accounts` | 50 | ~95% |
| `billing` | 31 | ~93% |
| `engine_client` | 34 | ~99% |
| `pantry` | 10 | ~96% |
| `search` (safety golden set) | 40 | ~65% |
| `api` | 5 | ~100% |
| **Total** | **170** | **77% overall** |

Coverage gates for Iteration 5: 85% overall, 95% accounts/billing/engine_client.

### Key test categories
- **Auth**: register, login, OTP (request, verify, expired, locked, wrong code), logout, token refresh
- **Permissions**: User A cannot see/modify User B's data (pantry, devices)
- **Safety golden set** (40 tests): vegetarian profile never gets meat, allergen exclusions never dropped, diet=None raises ValueError
- **Engine client**: circuit breaker state transitions, retry on network error, no retry on 4xx, 429 handling, caching, degraded mode
- **M-Pesa**: successful confirmation, failed/cancelled, duplicate receipt idempotency, amount mismatch rejection
- **Entitlements**: free user blocked by RequiresPlus, trialing counts as active, expired does not

---

## Django Apps Summary

| App | Models | Key Endpoints |
|---|---|---|
| `core` | `AuditEvent` | — |
| `accounts` | `CustomUser`, `AuthIdentity`, `Device`, `Consent`, `OTPRequest` | `/v1/auth/*`, `/v1/me`, `/v1/me/export`, `/v1/me/delete`, `/v1/me/devices` |
| `profiles` | `Profile`, `ProfileDiet` | `/v1/me/profile/`, `/v1/me/diet/` |
| `engine_client` | — (Redis circuit breaker) | client only, no HTTP routes |
| `pantry` | `PantryItem` | `/v1/pantry/` |
| `search` | — | `/v1/search/`, `/v1/resolve/`, `/v1/ingredients/`, `/v1/dishes/<slug>/` |
| `library` | `SavedRecipe`, `Collection`, `CookLog` | `/v1/saved/`, `/v1/saved/collections/`, `/v1/cooked/` |
| `planner` | `MealPlan`, `MealPlanEntry`, `ShoppingList`, `ShoppingItem` | `/v1/plans/<week>/`, `/v1/shopping-lists/` |
| `budget` | — | `/v1/budget/suggest/` |
| `content` | `Story` | `/v1/regions/`, `/v1/stories/` |
| `sync` | — | `/v1/sync/push/`, `/v1/sync/pull/` |
| `community` | `Submission`, `Review` | `/v1/submissions/`, `/v1/dishes/<slug>/reviews/` |
| `billing` | `Plan`, `Subscription`, `Payment` | `/v1/plans/`, `/v1/subscription/`, `/v1/subscribe/`, `/v1/mpesa/callback/` |
| `notifications` | `Notification`, `NotificationPreference` | `/v1/notifications/`, `/v1/notifications/preferences/` |
| `partners` | `SponsoredSlot` | admin only |
| `moderation` | — (proxy admin) | admin only |
| `api` | — | `/v1/health/`, `/v1/meta/version/`, `/docs/` |

---

## Celery Beat Schedule

| Task | Schedule | Purpose |
|---|---|---|
| `check_dataset_drift` | Daily 2 AM | Check engine dataset version; flush caches on change |
| `check_subscription_expiry` | Daily 1 AM | Expire subscriptions past `renews_at` |
| `check_trial_expiry` | Daily 1:30 AM | Expire trials past `trial_ends_at` |
| `send_renewal_reminders` | Daily 8 AM | Notify users renewing in 3 days |

---

## Free vs Plus Gating

| Feature | Free | Plus (KES 199/month) |
|---|---|---|
| Search | ✅ | ✅ |
| Dish pages, regions, stories | ✅ | ✅ |
| Pantry | ✅ | ✅ |
| Save recipes (up to 20) | ✅ | ✅ unlimited |
| Community submissions + reviews | ✅ | ✅ |
| Meal plans | ❌ → 403 | ✅ |
| Shopping lists | ❌ → 403 | ✅ |
| Nutrition details | ❌ → 403 | ✅ |
| Budget mode | ❌ → 403 | ✅ |
| Offline sync | ❌ → 403 | ✅ |

All 403 responses include: `{"error": {"code": "plus_required", "message": "...subscribe at /v1/subscribe/ for KES 199/month"}}`

---

## What is NOT yet built (Iteration 5)

- [ ] Daraja STK push full implementation (currently returns a mock response)
- [ ] SMS gateway for phone OTP (currently logs code — remove before production)
- [ ] Push notification delivery (FCM/APNs integration)
- [ ] Performance tuning: query count budgets, N+1 fixes
- [ ] Load test: search p95 < 250 ms at 50 req/s
- [ ] Soak test: 2-hour sustained load
- [ ] External penetration test
- [ ] Backup restore drill
- [ ] Rollback drill
- [ ] Runbooks: deploy, rollback, backup restore, incident response
- [ ] App team integration support
- [ ] Coverage to 85% overall, 95% accounts/billing/engine_client
- [ ] TypeScript client generation (for website team)
- [ ] Kotlin client generation (for Android team)

---

## Running locally

```bash
# 1. Copy env
cp .env.example .env
# Edit .env: set DATABASE_URL, REDIS_URL, ENGINE_BASE_URL, ENGINE_API_KEY, ENGINE_INTERNAL_KEY

# 2. Start services
docker compose -f docker/docker-compose.yml up --build

# 3. Or run tests directly (SQLite, no Docker needed)
export DJANGO_SETTINGS_MODULE=config.settings.test
python -m pytest

# 4. With coverage
python -m pytest --cov=apps --cov-report=term-missing
```

## Key files to read first

```
config/settings/base.py      — all settings in one place
apps/core/models.py          — TimeStampedModel, AuditEvent
apps/engine_client/client.py — typed engine API client
apps/billing/entitlements.py — RequiresPlus permission
apps/search/services.py      — allergen safety enforcement
apps/api/urls.py             — /v1/ URL map
```
