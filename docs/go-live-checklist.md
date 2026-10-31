# Go-Live Checklist — ff-consumer v1.0.0

**Sign-off required by:** Dog254 (repo owner)  
**Target tag:** `v1.0.0`  
**Date completed:** ___________

Mark each item ✅ before tagging v1.0.0. Any ❌ blocks the release.

---

## Engine Integration

- [ ] All engine endpoints used correctly (search, resolve, dish, ingredients, regions, pairings, substitutions, missing)
- [ ] Contract CI job green — `oasdiff` detects no breaking changes in engine OpenAPI
- [ ] Ambiguity flow tested — "unga" triggers choice picker, not a guess
- [ ] Engine 429 handled — `Retry-After` surfaced to user
- [ ] Engine outage handled — cached results served, `engine_status: degraded` in response
- [ ] Engine internal key (`ENGINE_INTERNAL_KEY`) works — community submission forwarding tested

## Safety

- [ ] Safety golden set: 40/40 passing (`pytest apps/search/tests/test_safety_golden_set.py`)
- [ ] Vegetarian profile never returns meat dishes — verified in golden set
- [ ] Excluded allergen never appears in results — verified in golden set
- [ ] Diet tags always injected on every search — code review confirmed, no bypass path

## Product — End-to-End Flows

- [ ] Register → verify email → login → get JWT ✅
- [ ] Phone OTP login flow tested
- [ ] Search with pantry injection returns personalised results
- [ ] Save a recipe, add to collection, view saved recipes
- [ ] Log a cook, view cook history
- [ ] Plan a full week (7 days × 3 meals)
- [ ] Generate shopping list from meal plan
- [ ] Check off items, share list as WhatsApp text
- [ ] Budget suggest returns dishes within KES limit
- [ ] Submit a community recipe → appears in moderation queue
- [ ] Approve submission → Celery forwards to engine
- [ ] Pay with M-Pesa/Paystack sandbox → Plus activates → gated features unlock
- [ ] `DELETE /me` → account soft-deleted → Celery purge task scheduled
- [ ] `GET /me/export` → returns JSON of all user data
- [ ] Offline sync: push pantry change, pull on second device — no data loss
- [ ] Taste of 47 Counties: at least 5 region stories visible via `GET /v1/stories/`

## Quality

- [ ] Overall test coverage ≥ 85% (`pytest --cov=apps`)
- [ ] `accounts` coverage ≥ 95%
- [ ] `billing` coverage ≥ 95%
- [ ] `engine_client` coverage ≥ 95%
- [ ] Permission isolation: 21 tests passing (`pytest apps/api/tests/test_permission_isolation.py`)
- [ ] Zero ruff lint errors (`ruff check .`)
- [ ] Zero mypy errors (`mypy apps/`)
- [ ] All migrations applied, no pending migrations (`python manage.py migrate --check`)
- [ ] OpenAPI schema valid, no drift (`python manage.py spectacular --validate`)

## Performance

- [ ] Load test: search p95 < 250ms at 50 req/s — **DONE: p95 = 39.9ms** ✅
- [ ] Soak test: 2-hour sustained load completed, no memory leaks, no error rate increase
- [ ] N+1 query fixes confirmed (planner, accounts export)

## Security

- [ ] Staff 2FA enforced — every staff account has TOTP enabled, verified in admin
- [ ] No open HIGH or CRITICAL findings from pen test / ZAP scan
- [ ] M-Pesa/Paystack callback: source IP validation + signature verification confirmed
- [ ] Payment duplicate callback tested — idempotent, no double activation
- [ ] Wrong payment amount tested — subscription not activated
- [ ] `ENGINE_API_KEY` and `ENGINE_INTERNAL_KEY` in secret manager, not in code or git
- [ ] `SECRET_KEY` rotated from any development value
- [ ] Admin path not publicly accessible (VPN/IP allowlist in prod)
- [ ] Signed commits on all release commits
- [ ] `gitleaks` pre-commit hook active, no secrets in history (TruffleHog scan clean)

## Privacy

- [ ] Consent records stored for every user (terms, privacy)
- [ ] Data export endpoint working (`GET /me/export`)
- [ ] Account deletion + grace period purge working (`DELETE /me`)
- [ ] Privacy notice URL set in settings
- [ ] Breach response procedure documented in `docs/runbooks/incident-response.md`
- [ ] Backup retention confirmed at 35 days

## Ops

- [ ] Deploy runbook tested — manual deploy executed successfully
- [ ] Rollback drill completed — broken deploy detected, rolled back, recovery confirmed
- [ ] Backup restore drill completed — DB restored from backup, data integrity verified
- [ ] Incident tabletop completed:
  - [ ] Engine outage scenario — consumer served cached data, degraded mode worked
  - [ ] Payment callback failure scenario — investigated, re-delivered webhook
- [ ] Celery workers running and processing tasks (`systemctl status celery-ff-consumer`)
- [ ] Celery beat running (`systemctl status celerybeat-ff-consumer`)
- [ ] Gunicorn running with 9 workers (`systemctl status ff-consumer.service`)
- [ ] Nightly CI jobs running (dependency scan, secret scan, DAST, safety golden set)
- [ ] Sentry configured and receiving errors
- [ ] Alerts configured for: health check failures, error rate spike, Celery queue backup

## Docs

- [ ] OpenAPI schema committed to `docs/openapi.yaml` (47 endpoints)
- [ ] README.md up to date with setup instructions
- [ ] Runbooks complete: deploy, rollback, backup-restore, incident-response
- [ ] Threat model documented in `docs/threat-model.md`
- [ ] At least one post-mortem template ready in `docs/post-mortems/`
- [ ] App team integration: website team can run in < 1 day using OpenAPI schema
- [ ] App team integration: Android team can run in < 1 day using OpenAPI schema

---

## Sign-off

| Role | Name | Date | Signature |
|---|---|---|---|
| Engineering lead / Owner | Dog254 | | |

**By signing, I confirm all items above are ✅ and the system is ready for v1.0.0.**

---

## Outstanding items at time of checklist creation (2026-10-31)

| Item | Status | Notes |
|---|---|---|
| Load test p95 < 250ms | ✅ Done | p95 = 39.9ms measured on server |
| Soak test 2-hour | ⬜ Pending | Run `./loadtests/run.sh soak` on server |
| Rollback drill | ⬜ Pending | See `docs/runbooks/rollback.md` |
| Backup restore drill | ⬜ Pending | See `docs/runbooks/backup-restore.md` |
| Incident tabletop | ⬜ Pending | 2 scenarios — engine outage + payment failure |
| Pen test / ZAP scan | ⬜ Pending | Nightly DAST job now in CI |
| Staff 2FA verified | ⬜ Pending | Check all staff accounts in admin |
| Threat model doc | ⬜ Pending | `docs/threat-model.md` not yet written |
| Taste of 47 Counties stories | ⬜ Pending | Content team — 5 counties minimum |
| App team integration | ⬜ Pending | Hand off `docs/openapi.yaml` |
