# Consumer Backend Sprint Plan

5 two-week iterations (~10 weeks). Each iteration ships to staging.

## Iteration 1 — Foundations (Weeks 1–2)

**Goal:** Django project up, users can register/login, engine client works, first engine call visible in staging.

### Build
- [ ] Repo structure from engine template (same layout: `apps/`, `config/`, `requirements/`, `docker/`, `docs/`)
- [ ] `core` app: `TimeStampedModel`, request ID middleware, error format, custom exception handler, pagination
- [ ] `accounts` app: `CustomUser` (email + phone), registration, email/password login, phone OTP login, JWT access + refresh tokens, logout, device registration
- [ ] `profiles` app: `Profile`, `ProfileDiet` — PATCH /me/profile and /me/diet
- [ ] `engine_client` app: typed client, `ENGINE_BASE_URL` + `ENGINE_API_KEY` from settings, health ping, version fetch, circuit breaker skeleton, cache layer
- [ ] `api` app: URL router `/v1/`, OpenAPI schema via drf-spectacular, `/v1/health/`, `/v1/meta/version/`
- [ ] Settings: base, dev, test, prod (same pattern as engine)
- [ ] docker-compose (web + db + redis + worker), Makefile, pyproject.toml tooling

### Security / CI/CD
- [ ] Org branch protection rules reused (from ff-engine CODEOWNERS pattern)
- [ ] pre-commit hooks (ruff, mypy, gitleaks)
- [ ] CI pipeline: lint, SAST (bandit), pip-audit, pytest, migration check, schema validation
- [ ] Staging on Render: free tier, Frankfurt region, PostgreSQL + Redis
- [ ] Staff 2FA enforced (django-two-factor-auth)
- [ ] Admin on separate path, blocked from public in prod
- [ ] Secret manager for `ENGINE_API_KEY` and `ENGINE_INTERNAL_KEY`

### Exit check
- Register a user, log in, get JWT, call `GET /v1/meta/version/` (which calls the engine) — see `dataset_version` in response
- First rollback practiced: deploy a broken build, auto-rollback triggers

---

## Iteration 2 — Search and Pantry (Weeks 3–4)

**Goal:** Core product works. User with a pantry can search for what to cook.

### Build
- [ ] `pantry` app: CRUD for pantry items (stores engine ingredient IDs)
- [ ] Engine client: `resolve()`, `search()`, `get_pairings()`, `get_substitutions()`, `get_missing()`, `get_ingredients()` (autocomplete)
- [ ] Ambiguity flow: when resolve returns `ambiguous`, return choices to client instead of guessing
- [ ] `POST /v1/resolve/` — wraps engine resolve
- [ ] `GET /v1/pantry/` + `POST` + `DELETE /v1/pantry/<id>/`
- [ ] `POST /v1/search/` — wraps engine search, injects pantry items + profile diet into request, adds personalisation layer (boost by user region, cook history)
- [ ] `GET /v1/ingredients/` — autocomplete (cached, debounced hint in OpenAPI)
- [ ] Engine cache: Redis keyed by `sha256(inputs + diet + dataset_version)`
- [ ] Circuit breaker: open after 5 failures, half-open after 30 seconds; degraded mode response
- [ ] `GET /v1/dishes/<slug>/` — proxy engine dish detail + cache with ETag

### Security
- [ ] Full PR pipeline running (all CI jobs)
- [ ] Engine contract job: runs against engine staging, fails on breaking OpenAPI change
- [ ] Rate limits per user + per IP per endpoint
- [ ] Permission tests: user A cannot see user B's pantry

### Exit check
- Pantry search returns exact/can_make/almost tiers with explained reasons
- "unga" (ambiguous) triggers choice picker, not a guess
- Vegetarian profile never returns meat dishes
- Excluded allergen never appears in results
- Engine-down: fallback returns cached results + `engine_status: degraded`

---

## Iteration 3 — Library, Planner, Offline (Weeks 5–6)

**Goal:** Users can save recipes, plan a week, generate a shopping list, and sync offline.

### Build
- [ ] `library` app: `SavedRecipe`, `Collection`, `CookLog` — CRUD + `POST /v1/cooked/`
- [ ] `planner` app: `MealPlan`, `MealPlanEntry`, `ShoppingList`, `ShoppingItem`
  - `GET/PUT /v1/plans/<week>/` — week is `YYYY-Www` format
  - `POST /v1/plans/<id>/shopping-list/` — generate from plan
  - `GET /v1/shopping-lists/<id>/share/` — returns WhatsApp-ready text
- [ ] `budget` app: `POST /v1/budget/suggest/` — takes KES amount + servings + diet, calls engine search with cost filter
- [ ] `content` app: `Story` model, `GET /v1/regions/` (proxies engine), `GET /v1/stories/`, `GET /v1/stories/<slug>/`
- [ ] `sync` app: `POST /v1/sync/push/`, `GET /v1/sync/pull?since=` — handles pantry, saved, cook_log, meal plans
- [ ] Dataset drift check: Celery beat task, nightly, calls engine `/v1/datasets/?since=<version>`, flags changed/removed saved recipes
- [ ] Audit log: append-only `AuditEvent`, shipped to external log store via Celery task

### Security
- [ ] Audit log wired and shipping
- [ ] Nightly DAST + fuzzing jobs added to CI
- [ ] OpenAPI docs complete; TypeScript client generated (for console/website team) and Kotlin client (for Android team)

### Exit check
- Plan a full week, generate a shopping list, check item off, share via WhatsApp text
- Edit pantry on two "devices" (simulate via two API tokens), sync without data loss
- Taste of 47 counties: at least 5 region stories visible via API

---

## Iteration 4 — Community, Money, Notifications (Weeks 7–8)

**Goal:** Users can submit recipes, pay for Plus, and receive notifications.

### Build
- [ ] `community` app:
  - `POST /v1/submissions/` — creates draft, validates required fields, queues for moderation
  - `GET /v1/submissions/` — user's own submissions with status
  - `POST /v1/dishes/<slug>/reviews/` — rating + text, queued for moderation
  - Celery worker: on moderation approval, forwards submission to engine `POST /v1/internal/submissions/` using `ENGINE_INTERNAL_KEY`
- [ ] `billing` app:
  - `GET /v1/plans/` — returns Free and Plus plan details
  - `POST /v1/subscribe/` — triggers M-Pesa STK push
  - `POST /v1/mpesa/callback/` — verifies signature, confirms payment, activates Plus
  - `GET /v1/subscription/` — current plan, renews_at, trial status
  - Entitlement checks on gated endpoints (meal plans, nutrition, offline sync)
  - Celery beat: renewal reminders, expiry checks
- [ ] `notifications` app: push token registration, in-app notifications table, preference CRUD
- [ ] `partners` app: sponsored slot model (dish_id or ingredient_id, start/end dates, label)
- [ ] `moderation` app: admin queue for submissions and reviews, audit trail

### Security
- [ ] M-Pesa callback: source IP validation + signature verification
- [ ] Payment tests: duplicate callback, wrong amount, expired sub, timeout
- [ ] Step-up 2FA for staff: moderation approve/reject requires re-auth confirmation
- [ ] Data export endpoint: `GET /me/export` — returns user's data as JSON
- [ ] Account deletion: `DELETE /me` — soft delete, Celery task purges after grace period
- [ ] Consent records stored and queryable
- [ ] Threat model review (document in `docs/threat-model.md`)

### Exit check
- Pay with M-Pesa sandbox → Plus activates → meal plans and nutrition unlock
- Submit a recipe → appears in moderation queue → approve → Celery forwards to engine
- `DELETE /me` → user data purged after grace period, audit event logged

---

## Iteration 5 — Hardening and Release (Weeks 9–10)

**Goal:** v1.0.0 — production-ready, app teams integrated.

### Build
- [ ] Bug fixes from iterations 1–4
- [ ] Performance tuning (query count budgets, N+1 fixes)
- [ ] Runbooks: deploy, rollback, backup restore, incident response
- [ ] Final API freeze: no breaking changes after this point for v1
- [ ] App team integration support (website + Android consuming generated clients)

### Security / Ops
- [ ] Load test: search p95 < 250 ms at 50 req/s on staging
- [ ] Soak test: 2-hour sustained load
- [ ] External penetration test — fix all high/critical findings
- [ ] Backup restore drill: restore staging DB from backup, verify data integrity
- [ ] Rollback drill: deploy v1.0.0-rc1, roll back to previous, verify health
- [ ] Incident tabletop: simulate engine outage, payment callback failure
- [ ] Go-live checklist signed by owner

### Exit Criteria (all must be ✅ before v1.0.0 tag)

| Area | Criterion |
|---|---|
| Engine integration | All engine endpoints used correctly; contract job green; ambiguity, 429, outage paths proven |
| Safety | Vegetarian/allergen golden set at 100%; zero unfiltered searches for profiles with exclusions |
| Product | Search, pantry, saved, planner, shopping, budget, community, Plus billing, offline sync — all E2E |
| Quality | Coverage gates met (85% overall, 95% accounts/billing/engine_client); property + permission tests green |
| Performance | Search p95 < 250 ms at 50 req/s on staging |
| Security | 2FA on every staff account; no open high/critical; pen test fixed; go-live checklist signed |
| Privacy | Consent, export, deletion, privacy notice, breach procedure in place |
| Ops | Signed images only; rollback + restore drills passed; dashboards + alerts live; runbooks complete |
| Docs | OpenAPI complete; app teams integrate in under a day |

---

## Parallel Tracks

While backend runs Iterations 1–5:
- **Content team:** Write Taste of 47 counties stories; target 10 counties for launch
- **App team:** Consume generated TypeScript client (from Iteration 3) for website; Kotlin client for Android

---

## Week 1 Decisions (lock these before writing code)

1. **Login methods at launch:** phone OTP + email/password ← *recommended, agreed*
2. **Free tier:** search is free; Plus gates meal plans, nutrition, offline sync, later AI ← *agreed*
3. **Plus price:** KES 199/month ← *agreed*
4. **Trial length:** 14 days or 30 days? — *decide before billing app*
5. **Moderation:** who reviews submissions? turnaround SLA?
6. **Taste of 47 counties:** who writes the stories? which 5–10 counties launch first?
7. **Shopping list prices:** engine cost estimates only for v1 (no external price source) ← *recommended*
8. **Staging:** Render (Frankfurt) ← *agreed*
9. **One team or two?** Consumer backend + engine same team ← *assumed yes*
