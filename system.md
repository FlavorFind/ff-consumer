# ff-consumer — System Reference

> **Read this at the start of every session instead of running context-gatherer.**
> Update this file whenever you change something significant.

---

## What this is

`ff-consumer` is the Django/DRF backend that serves the Flavor Find Android app and website.
It owns everything about **people**: accounts, pantries, meal plans, saved recipes, subscriptions, community.
It owns **nothing about food** — all food data comes from the Recipe Engine (`ff-engine`) via API.

**The two-system rule:**
```
Consumer Backend  ──── X ──── Engine DB   (never direct)
Consumer Backend  ──────────► Engine API  (only route)
```

---

## Servers

| Thing | Value |
|---|---|
| Self-hosted server | `mayday@100.96.139.83` (Tailscale) |
| SSH | `ssh -o StrictHostKeyChecking=no mayday@100.96.139.83` |
| Consumer path on server | `/home/mayday/ff-consumer` |
| Engine path on server | `/home/mayday/ff-engine` |
| Consumer service | `ff-consumer.service` (systemd, 9 gunicorn workers on `127.0.0.1:8001`) |
| Restart command | `sudo systemctl restart ff-consumer` |
| Settings on server | `config.settings.prod` (set via `.env`, but `manage.py` defaults to `dev` — always pass `DJANGO_SETTINGS_MODULE=config.settings.prod` explicitly on server) |
| Engine URL | `https://engine.flavorfind.co.ke` |
| Engine health | `GET https://engine.flavorfind.co.ke/v1/health/` |
| Engine docs | `https://engine.flavorfind.co.ke/docs/` |
| Engine version | `1.0.0`, dataset `2026.10.0` |

**Deploy pattern:**
```bash
ssh mayday@100.96.139.83
cd /home/mayday/ff-consumer
git pull origin main
DJANGO_SETTINGS_MODULE=config.settings.prod .venv/bin/pip install -q -r requirements/prod.txt --prefer-binary
DJANGO_SETTINGS_MODULE=config.settings.prod .venv/bin/python manage.py migrate --no-input
DJANGO_SETTINGS_MODULE=config.settings.prod .venv/bin/python manage.py collectstatic --no-input -v 0
sudo systemctl restart ff-consumer
```

---

## Stack

| Layer | Version |
|---|---|
| Python | 3.14 (server), 3.12 (local dev) |
| Django | 5.2.x |
| DRF | 3.18.x |
| PostgreSQL | 16 (own DB, never shared with engine) |
| Redis | 7 |
| Celery | 5.4.0 + django-celery-beat |
| Auth (users) | Argon2id passwords + JWT (simplejwt) |
| Auth (staff) | Django sessions + django-two-factor-auth (TOTP mandatory) |
| Payments | Paystack Daraja (NOT M-Pesa — changed from original plan) |
| Email | Resend API (direct HTTP, no Django email backend) |
| API docs | drf-spectacular 0.30.0 at `/docs/` |
| Linting | ruff |
| Type checking | mypy |
| Testing | pytest + pytest-django |

---

## Django Apps

| App | Purpose | Has models? |
|---|---|---|
| `core` | `TimeStampedModel`, `SoftDeleteModel`, `AuditEvent`, `log_audit_event()`, middleware, pagination, exceptions | ✅ |
| `accounts` | `CustomUser`, registration, login, JWT, email verification, devices, consent, export, delete | ✅ |
| `profiles` | `Profile` (household, region, budget), `ProfileDiet` (diet tags + allergen exclusions) | ✅ |
| `engine_client` | Typed `EngineClient` singleton — the only place engine API is called | ❌ |
| `pantry` | `PantryItem` — stores engine ingredient IDs + display names | ✅ |
| `search` | Wraps engine search + pantry injection + region boost | ❌ |
| `library` | `SavedRecipe`, `Collection`, `CookLog` | ✅ |
| `planner` | `MealPlan`, `MealPlanEntry`, `ShoppingList`, `ShoppingItem` | ✅ |
| `budget` | Budget mode — filters engine results by KES budget | ❌ |
| `content` | `Story` model, Taste of 47 counties editorial | ✅ |
| `community` | `Submission` (recipe drafts → engine), `Review` (dish ratings) | ✅ |
| `billing` | `Plan`, `Subscription`, `Payment` — Paystack checkout + webhook | ✅ |
| `notifications` | `Notification`, `NotificationPreference` | ✅ |
| `partners` | `SponsoredSlot` | ✅ |
| `sync` | Offline sync push/pull for Android | ❌ |
| `moderation` | Admin queue for submissions and reviews | ❌ |
| `api` | URL router for `/v1/` | ❌ |
| `admin_api` | Internal `/v1/admin/` endpoints (service token auth) | ❌ |

---

## URL Structure

### Root URLs (`config/urls.py`)

```
GET  /                            → landing page (inline HTML)
     /                            → two_factor staff login URLs
     /v1/                         → all API endpoints (apps.api.urls)
     /v1/admin/                   → internal admin API (service token)
     /v1/schema/                  → OpenAPI schema (SpectacularAPIView)
     /docs/                       → Swagger UI
     /verify                      → browser fallback for email verification deep link (HTML page)
     /.well-known/assetlinks.json → Android App Links asset file (JSON)
     /admin/                      → Django admin (only if ADMIN_ENABLED=True)
     /__debug__/                  → debug toolbar (DEBUG=True only)
```

### API endpoints (`/v1/`)

**Auth & Users**
```
POST   /v1/auth/register/              → create account, sends verification email, returns {access, refresh, user}
POST   /v1/auth/verify-email/          → submit token from email → {user with email_verified: true}
POST   /v1/auth/resend-verification/   → resend verification email
POST   /v1/auth/login/                 → email+password → {access, refresh, user}
POST   /v1/auth/refresh/               → rotate refresh token
POST   /v1/auth/logout/                → blacklist refresh token
GET    /v1/me/                         → current user object
GET    /v1/me/export/                  → all user data as JSON
DELETE /v1/me/delete/                  → soft-delete, purge after 35 days
GET    /v1/me/devices/                 → list registered devices
POST   /v1/me/devices/                 → register device (platform + push_token)
DELETE /v1/me/devices/<uuid>/          → remove device
```

**Profile**
```
GET/PATCH  /v1/me/profile/   → household_size, region_slug, budget_kes_per_meal
GET/POST   /v1/me/diet/      → diet tags and allergen exclusions
DELETE     /v1/me/diet/<id>/ → remove a diet tag
```

**Pantry**
```
GET    /v1/pantry/       → list pantry items
POST   /v1/pantry/       → add ingredient (ingredient_id, ingredient_slug, display_name)
DELETE /v1/pantry/<id>/  → remove ingredient
```

**Search & Ingredients**
```
POST /v1/search/        → recipe search (public: 5 results, free: 20, plus: 50)
POST /v1/resolve/       → resolve free-text tokens to engine ingredient IDs
GET  /v1/ingredients/   → autocomplete (?q=&lang=)
GET  /v1/dishes/<slug>/ → dish detail (public, cached)
```

**Library**
```
GET/POST   /v1/saved/              → saved recipes (free: max 20, plus: unlimited)
DELETE     /v1/saved/<id>/         → unsave
GET/POST   /v1/collections/        → recipe collections
DELETE     /v1/collections/<id>/   → delete collection
POST       /v1/cooked/             → log cooking a dish
GET        /v1/cooked/             → cook log history
```

**Planner** *(Plus only)*
```
GET/PUT    /v1/plans/<week>/                    → week is YYYY-Www format
POST       /v1/plans/<id>/shopping-list/        → generate shopping list from plan
GET        /v1/shopping-lists/                   → list user's shopping lists
GET/PATCH  /v1/shopping-lists/<id>/             → shopping list detail
GET        /v1/shopping-lists/<id>/share/        → WhatsApp-ready text
PATCH      /v1/shopping-lists/<id>/items/<iid>/ → check/uncheck item
```

**Budget** *(Plus only)*
```
POST /v1/budget/suggest/   → KES amount + servings + diet → engine search with cost filter
```

**Content**
```
GET /v1/regions/           → engine regions (47 counties + neighbours)
GET /v1/stories/           → editorial stories
GET /v1/stories/<slug>/    → story detail
```

**Community**
```
POST /v1/submissions/              → create draft submission
GET  /v1/submissions/              → user's own submissions
GET  /v1/dishes/<slug>/reviews/    → dish reviews
POST /v1/dishes/<slug>/reviews/    → submit a review (1–5 stars)
```

**Billing**
```
GET  /v1/plans/               → list Free and Plus plans
POST /v1/subscribe/           → init Paystack transaction → {authorization_url, reference}
GET  /v1/subscription/        → current subscription status
POST /v1/subscription/cancel/ → cancel subscription
POST /v1/paystack/webhook/    → Paystack event webhook (HMAC-SHA512 verified, no auth)
```

**Sync** *(Plus only)*
```
POST /v1/sync/push/      → client sends array of changes
GET  /v1/sync/pull/      → ?since=<timestamp> → server changes since last sync
```

**Notifications**
```
GET/PATCH /v1/notifications/preferences/   → push_enabled, email_enabled, quiet hours
GET       /v1/notifications/               → in-app notification list
POST      /v1/notifications/<id>/read/     → mark as read
```

**Health / Meta**
```
GET /v1/health/        → {status, service, version} — no auth required
GET /v1/meta/version/  → {consumer_version, engine_version, dataset_version, engine_status}
```

---

## Data Models

### accounts

```python
CustomUser
  id (UUID PK), email (unique), username (unique, max 50),
  language ("en"|"sw"), status ("active"|"suspended"|"deleted"),
  email_verified (bool), is_staff, is_active,
  created_at, updated_at, deleted_at (soft delete)
  USERNAME_FIELD = "email"
  Passwords: Argon2id

EmailVerification
  id (UUID), user (FK), token (SHA-256 hash of plain token, never stored plain),
  created_at, expires_at (24h TTL), used_at (one-time use)

AuthIdentity
  user (FK), provider ("password"), verified_at   # phone OTP not yet implemented

Device
  user (FK), platform ("android"|"ios"|"web"), push_token,
  last_seen (auto_now), last_sync_at, created_at

Consent
  user (FK), type ("terms"|"privacy"|"marketing"), version, granted_at, revoked_at
```

### profiles

```python
Profile
  user (OneToOne), household_size, region_slug, budget_kes_per_meal, updated_at

ProfileDiet
  user (FK), diet_tag_slug (engine slug, e.g. "vegetarian", "nut-free"),
  source ("user_set"|"allergen")
  # SAFETY: these are injected on every engine search call for authenticated users
```

### pantry

```python
PantryItem
  user (FK), ingredient_id (engine UUID), ingredient_slug (engine slug),
  display_name (cached from engine), added_at, expires_on
  # unique_together: (user, ingredient_id)
  # Quantities NOT stored — engine ignores them in v1
```

### library

```python
Collection
  user (FK), name, created_at, updated_at
  # unique_together: (user, name)

SavedRecipe
  user (FK), dish_id (engine UUID), dish_slug,
  dataset_version (stored for drift detection),
  collection (FK nullable), note, saved_at
  # Free: max 20. Plus: unlimited.

CookLog
  user (FK), dish_id, dish_slug, cooked_at, rating (1–5), note
```

### planner

```python
MealPlan
  user (FK), week_start (date, always Monday)
  # unique_together: (user, week_start)

MealPlanEntry
  plan (FK), day ("mon"–"sun"), meal_type ("breakfast"|"lunch"|"dinner"|"snack"),
  dish_id, dish_slug, servings, note, position

ShoppingList
  user (FK), plan (FK nullable), name, created_at

ShoppingItem
  shopping_list (FK), ingredient_id, ingredient_slug, display_name,
  quantity_note, checked (bool), price_estimate_kes (nullable), position
```

### community

```python
Submission
  user (FK), payload (JSON), engine_submission_id (nullable — set after engine forward),
  status ("draft"→"sent"→"in_review"→"accepted"|"rejected"), reason

Review
  user (FK), dish_id, dish_slug, stars (1–5), text,
  status ("pending"|"approved"|"rejected"), reason
  # unique_together: (user, dish_id)
```

### billing

```python
Plan
  code (PK: "free"|"plus"), name, price_kes (0 for free), features (JSON list)

Subscription
  user (OneToOne), plan (FK), status ("pending"|"active"|"trialing"|"cancelled"|"expired"),
  trial_ends_at, renews_at, cancelled_at
  # Subscription starts as PENDING — only the verified Paystack webhook activates it

Payment
  user (FK), subscription (FK), provider ("paystack"),
  provider_ref (payment UUID, used as Paystack reference + idempotency key),
  checkout_url, amount_kes, status ("pending"|"confirmed"|"failed"),
  receipt_no (Paystack transaction ID), confirmed_at
```

### notifications

```python
Notification
  user (FK), channel ("push"|"email"|"in_app"), type, title, body,
  data (JSON), read_at, sent_at

NotificationPreference
  user (OneToOne), push_enabled, email_enabled, quiet_hours_start, quiet_hours_end
```

### core

```python
AuditEvent   # append-only, never update/delete
  actor_id (UUID), actor_type ("user"|"staff"|"system"), action,
  object_type, object_id, before_data (JSON), after_data (JSON),
  reason, ip_address, created_at
  # Shipped to external log store via Celery task on creation
```

---

## Engine Client (`apps/engine_client/client.py`)

Single module-level singleton: `from apps.engine_client.client import engine`

**Methods:**
```python
engine.search(ingredients, diet, mode, exclude, lang, limit, meal_type)
engine.resolve(tokens, lang)           # NOTE: engine field is "ingredients" not "tokens"
engine.get_ingredients(q, lang)
engine.get_dish(slug, lang)
engine.get_pairings(slug)
engine.get_substitutions(slug)
engine.get_missing(slug, pantry_ingredient_ids)
engine.get_regions(lang)
engine.get_version()
engine.health_ping()
engine.submit_community(payload)       # uses internal_key
engine.get_dataset_diff(since_version)
engine.get_dataset_version()           # cached 1h in Redis
```

**Circuit breaker** (state in Redis):
- Keys: `ffconsumer:engine:circuit_state`, `ffconsumer:engine:circuit_failures`, `ffconsumer:engine:circuit_opened_at`
- Opens after 5 consecutive failures, half-open after 30 seconds
- On open: `EngineUnavailableError` — search returns `{"engine_status": "degraded"}`

**Cache keys** (all prefixed `ffconsumer:`):
- Search: `ffconsumer:search:<sha256(sorted_ingredients+diet+mode+dataset_version)>` — 5 min TTL
- Dish: `ffconsumer:dish:<slug>:<dataset_version>` — 1h TTL
- Ingredient autocomplete: `ffconsumer:ingredient_ac:<q>:<lang>` — 10 min TTL
- Regions: `ffconsumer:regions:<lang>` — 24h TTL
- Dataset version: `ffconsumer:engine:dataset_version` — 1h TTL

---

## Search Safety Rules (non-negotiable)

1. `diet` must NEVER be `None` — raises `ValueError` at the engine client level
2. For authenticated users, `ProfileDiet` tags are always injected before every search call
3. Anonymous users get unfiltered results (they have no profile), capped at `ANONYMOUS_RESULT_LIMIT = 5`
4. Free users capped at `FREE_RESULT_LIMIT = 20`
5. Plus users capped at `PLUS_RESULT_LIMIT = 50`
6. Every search response includes `allergen_disclaimer`: *"Allergen information is for guidance only. Always confirm with the kitchen before ordering."*

---

## Auth Architecture

### End users (JWT)
- Registration → email+password → `email_verified=False`, login works immediately
- Login → `POST /v1/auth/login/` → `{access (15 min), refresh (30 days)}`
- Refresh tokens rotate and are blacklisted on rotation
- `Authorization: Bearer <access_token>` on all authenticated endpoints

### Email verification
- Token: `secrets.token_hex(32)` — 64 hex chars
- Only SHA-256 hash stored in DB; plain token only ever in memory and in email
- 24h TTL, one-time use, previous tokens deleted on resend
- Email CTA: `flavorfind://verify?token=<plain>` (Android intercepts)
- Fallback link in email: `https://app.flavorfind.co.ke/verify?token=<plain>` (browser)
- Browser verify page: `GET /verify?token=` — calls same logic, returns HTML

### Android deep link setup
- Custom scheme: `flavorfind://verify?token=<token>` — works immediately, no server config needed
- HTTPS App Links: `GET /.well-known/assetlinks.json` — served by Django, needs `ANDROID_CERT_SHA256` set to release keystore SHA-256 fingerprint
- `ANDROID_CERT_SHA256` is currently empty → App Links not verified, custom scheme still works

### Staff (Django sessions)
- Login via `two_factor:login` — TOTP mandatory, no SMS/email fallback
- Admin at `/admin/` — controlled by `ADMIN_ENABLED` env var

---

## Billing (Paystack — not M-Pesa)

> **Note:** The original plan was M-Pesa Daraja. The implementation uses Paystack instead.

**Flow:**
```
POST /v1/subscribe/
  → subscription created with status=PENDING
  → payment created with status=PENDING
  → backend calls Paystack Initialize Transaction API
  → returns {authorization_url} to client
  → client redirects user to authorization_url
  → user pays on Paystack hosted page
  → Paystack POSTs charge.success to POST /v1/paystack/webhook/
  → webhook: verify HMAC-SHA512 signature
  → verify amount server-side (never trust webhook amount alone)
  → only confirm PENDING payments (idempotent)
  → payment → CONFIRMED, subscription → ACTIVE, renews_at = now + 30 days
```

**Paystack reference** = `payment.id` (UUID) — used as idempotency key

**Security:**
- Signature: `HMAC-SHA512(PAYSTACK_SECRET_KEY, raw_body)` verified against `X-Paystack-Signature`
- Amount: re-verified against `payment.amount_kes` (tolerance 0.01 KES)
- Idempotency: webhook only processes `PENDING` payments; duplicates silently ignored
- Webhook returns 200 always (Paystack retries on non-200)

**Plus price:** KES 199/month

**Entitlements** (`apps/billing/entitlements.py`):
```python
user_has_active_plus(user) → bool
RequiresPlus              # DRF permission class — 403 with clear message if not Plus
```

**Plus gates:** meal_plans, shopping_lists, nutrition_details, budget_mode, offline_sync, unlimited_saves (free: max 20 saved recipes)

---

## Celery Tasks

Scheduled (via django-celery-beat, `Africa/Nairobi` timezone):

| Task | Schedule | File |
|---|---|---|
| `check_dataset_drift` | 2:00 AM daily | `apps.engine_client.tasks` |
| `check_subscription_expiry` | 1:00 AM daily | `apps.billing.tasks` |
| `check_trial_expiry` | 1:30 AM daily | `apps.billing.tasks` |
| `send_renewal_reminders` | 8:00 AM daily | `apps.billing.tasks` |

One-shot tasks:
- `purge_user_data_after_grace_period(user_id)` — fires 35 days after `DELETE /me/delete/`
- `ship_audit_event(event_id)` — fires on every `log_audit_event()` call

---

## Settings Reference

Key env vars (see `.env.example` for full list):

| Var | Default | Notes |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.dev` | Server uses `prod`; pass explicitly with `manage.py` |
| `SECRET_KEY` | — | Required |
| `DATABASE_URL` | — | Required |
| `REDIS_URL` | `redis://localhost:6379/0` | |
| `ENGINE_BASE_URL` | `https://engine.flavorfind.co.ke` | |
| `ENGINE_API_KEY` | `""` | Scopes: `read:search`, `read:catalog` |
| `ENGINE_INTERNAL_KEY` | `""` | Scope: `internal:curation` |
| `RESEND_API_KEY` | `""` | Empty = skip email silently (dev safe) |
| `RESEND_FROM_EMAIL` | `Flavor Find <onboarding@resend.dev>` | Change after domain verification |
| `FRONTEND_URL` | `https://flavorfind.co.ke` | Used in some legacy links |
| `APP_BASE_URL` | `https://app.flavorfind.co.ke` | Used in verification email fallback link |
| `ANDROID_CERT_SHA256` | `""` | Release cert fingerprint for App Links; empty = safe |
| `PAYSTACK_SECRET_KEY` | `""` | Empty = mock response in dev |
| `PAYSTACK_PUBLIC_KEY` | `""` | |
| `PAYSTACK_CALLBACK_URL` | `https://flavorfind.co.ke/plus/success` | |
| `ADMIN_ENABLED` | `True` | Set `False` in prod to block `/admin/` |
| `SENTRY_DSN` | `""` | Empty = Sentry disabled |
| `CONSUMER_VERSION` | `dev` | Set by CI/CD |
| `THROTTLE_ANON` | `60/minute` | |
| `THROTTLE_USER` | `300/minute` | |

---

## CI/CD

**GitHub Actions workflows:**

| File | Trigger | Jobs |
|---|---|---|
| `.github/workflows/ci.yml` | PR + push to main | lint (ruff), sast (bandit), pip-audit, pytest, migrate check, schema validate |
| `.github/workflows/deploy-staging.yml` | Push to main (after CI) | Tailscale → SSH → git pull → pip install → migrate → collectstatic → restart |
| `.github/workflows/nightly.yml` | Cron | DAST, engine contract check |

**Branch protection on `main`:**
- Require PR + 1 approval
- All CI checks must pass
- No direct push

**Coverage gates:**
- Overall: 85%
- `accounts`, `billing`, `engine_client`: 95%

---

## Git Status & Recent History

As of last update (2026-11-15):

```
acd2f57 chore: ignore .hypothesis/ directory
359bd4b feat: email verification deep link support for Android
606f85e fix: billing hardening, search safety, pantry, sync, contract tests, type fixes
800ec20 feat: Phase 3 — consumer admin API (/v1/admin/)
38964b1 docs: soak test results, go-live checklist sign-off, search cache comment
```

Working tree: **clean** on both local and server (`origin/main` = server = local).

---

## Known Gaps / Not Yet Implemented

- Phone OTP login — `AuthIdentity.Provider` has `PASSWORD` only; phone field not on `CustomUser`
- `ANDROID_CERT_SHA256` is empty — HTTPS App Links unverified (custom scheme works fine)
- `RESEND_FROM_EMAIL` is `onboarding@resend.dev` — change after `flavorfind.co.ke` verified on Resend
- Trial length undecided (14 or 30 days) — `Subscription.trialing` status exists, not wired to signup flow
- Moderation staffing/SLA not decided
- Taste of 47 counties stories — content not yet written
- Render staging (Frankfurt) not yet configured — only self-hosted server active

---

## Development Workflow

```bash
# Local
make up           # docker compose up --build
make test         # pytest in container
make lint         # ruff check
make format       # ruff format
make typecheck    # mypy apps/
make migrate      # python manage.py migrate
make shell        # python manage.py shell

# Direct (venv activated)
pytest --tb=short -q
ruff check apps/
```

**Running manage.py locally:**
```bash
# .env is auto-loaded by settings; defaults to dev settings
python manage.py migrate
python manage.py shell
```

**Running manage.py on server (always pass prod settings):**
```bash
DJANGO_SETTINGS_MODULE=config.settings.prod .venv/bin/python manage.py <command>
```
