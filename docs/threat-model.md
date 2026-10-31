# Threat Model — ff-consumer v1.0.0

**Author:** FlavorFind engineering team  
**Date:** 2026-11-01  
**System:** Flavor Find Consumer Backend (`FlavorFind/ff-consumer`)  
**Scope:** Consumer API, authentication, payments, engine integration, data storage  
**Method:** STRIDE (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege)

---

## 1. System Overview

```
                    ┌─────────────────────────────────┐
  Android / Web ───►│   ff-consumer (this system)     │──► PostgreSQL (user data)
                    │   Django/DRF, Gunicorn           │──► Redis (cache, queue)
                    │   Tailscale + UFW                │──► Celery workers
                    └──────────────┬──────────────────┘
                                   │ X-API-Key (read:search, read:catalog)
                                   ▼
                    ┌─────────────────────────────────┐
                    │   ff-engine (external)           │
                    │   engine.flavorfind.co.ke        │
                    └─────────────────────────────────┘
                                   ▲
                    ┌──────────────┘  X-API-Key (internal:curation)
                    │  Celery worker (community submissions only)
```

**Trust boundaries:**
1. Public internet → consumer API (JWT authentication required for most endpoints)
2. Consumer API → engine API (API key authentication, read-only for most calls)
3. Paystack → consumer API webhook (HMAC-SHA512 signature verification)
4. Tailscale network → SSH access (only route to the server shell)

**What this system owns:** user accounts, pantries, meal plans, saved recipes, billing, community submissions  
**What this system does NOT own:** food data — dishes, ingredients, recipes all live in the engine

---

## 2. Assets

| Asset | Sensitivity | Where stored |
|---|---|---|
| User passwords | Critical | PostgreSQL, Argon2id hashed |
| JWT refresh tokens | High | PostgreSQL (revocable) |
| Phone numbers | High | PostgreSQL |
| Email addresses | Medium | PostgreSQL |
| Payment records (M-Pesa/Paystack refs) | High | PostgreSQL — no card data ever stored |
| Engine API keys | Critical | Server `.env`, Render secrets — never in code |
| `ENGINE_INTERNAL_KEY` | Critical | Server `.env`, Render secrets — never in code |
| `PAYSTACK_SECRET_KEY` | Critical | Server `.env`, Render secrets |
| Django `SECRET_KEY` | Critical | Server `.env`, Render secrets |
| User pantry and diet data | Medium | PostgreSQL |
| Audit log | High | PostgreSQL + shipped to external log store |
| Consent records | Medium | PostgreSQL |

---

## 3. Threat Analysis (STRIDE)

### 3.1 Spoofing

#### T-S1 — Attacker impersonates a logged-in user by forging a JWT

**Likelihood:** Low  
**Impact:** Critical — full account takeover

**Mitigations in place:**
- JWTs signed with `SECRET_KEY` (HS256) — unforgeable without the key
- `SECRET_KEY` is 50+ random characters, stored only in secrets manager
- Access tokens expire in 15 minutes — small window even if intercepted
- Refresh tokens stored in DB — can be revoked per-device on logout
- `ROTATE_REFRESH_TOKENS = True` — each refresh issues a new token, old one invalidated

**Residual risk:** If `SECRET_KEY` is compromised, all tokens can be forged. Mitigation: rotate `SECRET_KEY` immediately on any suspected compromise — this invalidates all existing tokens forcing all users to re-login.

---

#### T-S2 — Attacker replays a stolen access token

**Likelihood:** Medium (token could be intercepted on non-HTTPS connection)  
**Impact:** High — acts as the victim user for up to 15 minutes

**Mitigations in place:**
- All traffic over HTTPS (TLS enforced via Cloudflare + `SECURE_SSL_REDIRECT`)
- 15-minute access token TTL limits replay window
- HSTS header prevents downgrade to HTTP

**Residual risk:** Low. Requires MITM on a TLS-protected connection.

---

#### T-S3 — Attacker spoofs a Paystack webhook callback

**Likelihood:** Medium — webhook URL is publicly known  
**Impact:** Critical — could fraudulently activate Plus subscriptions

**Mitigations in place:**
- HMAC-SHA512 signature verified before any processing (`_verify_paystack_signature`)
- Amount re-verified server-side against `Plan.price_kes` — callback amount alone cannot trigger activation
- Bad signature → event silently ignored, 200 returned (stops Paystack retries), no processing
- Live tested 2026-10-31: forged signature correctly rejected ✅

**Residual risk:** If `PAYSTACK_SECRET_KEY` is leaked, signatures can be forged. Mitigation: rotate key immediately via Paystack dashboard.

---

#### T-S4 — Attacker impersonates the engine (DNS/MITM)

**Likelihood:** Very low  
**Impact:** High — could serve malicious food data

**Mitigations in place:**
- Engine URL is pinned in settings (`ENGINE_BASE_URL`)
- TLS certificate validation enabled (Python `requests` default)
- Engine responses cached — MITM would need to bypass cache timing

**Residual risk:** Very low. Standard TLS CA trust model.

---

### 3.2 Tampering

#### T-T1 — Attacker modifies pantry/diet data in transit to bypass allergen filter

**Likelihood:** Low  
**Impact:** Critical — safety violation, user receives food they're allergic to

**Mitigations in place:**
- Diet/allergen tags are injected server-side from `ProfileDiet` — never taken from the request body
- The `SearchView` always fetches `ProfileDiet.objects.filter(user=request.user)` before calling the engine
- Safety golden set: 40 automated tests verify allergen injection — run in CI and nightly
- Code path: client cannot submit a `diet` field to `/v1/search/` that overrides profile tags

**Residual risk:** Negligible. Diet injection is server-side only. The client has no way to suppress it.

---

#### T-T2 — Attacker tampers with a payment callback amount

**Likelihood:** Medium  
**Impact:** High — activate Plus by paying less than KES 199

**Mitigations in place:**
- Amount in callback is ignored for activation decision
- Server fetches `Plan.price_kes` from DB and compares to `payment.amount_kes` recorded at STK push time
- Mismatch → payment marked `failed`, audit event logged, subscription not activated

**Residual risk:** Low. Amount verification is double-layered (at callback receipt and at activation).

---

#### T-T3 — Attacker modifies a community submission after it's approved

**Likelihood:** Low  
**Impact:** Medium — malicious content reaches the engine

**Mitigations in place:**
- Submissions stored as immutable JSON payload at creation time
- Status transitions are append-only (`draft → sent → in_review → accepted/rejected`)
- Celery worker forwards the stored payload, not a re-fetched version
- Engine has its own moderation layer for internal submissions

**Residual risk:** Low. Payload is frozen at submission time.

---

### 3.3 Repudiation

#### T-R1 — User denies making a payment or submitting a recipe

**Likelihood:** Medium (billing disputes are common)  
**Impact:** Medium — financial or legal dispute

**Mitigations in place:**
- `AuditEvent` written for every payment confirmation, subscription change, and submission action
- Audit log is append-only — records cannot be edited or deleted
- Audit log shipped to external log store via Celery (survives local DB loss)
- Payment records include Paystack/M-Pesa `provider_ref` — cross-referenceable with payment provider records

**Residual risk:** Low. Dual-source evidence (our audit log + Paystack/Safaricom records).

---

#### T-R2 — Staff denies approving/rejecting a community submission

**Likelihood:** Low  
**Impact:** Medium — moderation accountability

**Mitigations in place:**
- Every approve/reject writes an `AuditEvent` with `actor_id` (staff user), action, object, and timestamp
- Staff 2FA mandatory — identity is strongly verified before any moderation action
- Django admin session tied to authenticated staff account

**Residual risk:** Low.

---

### 3.4 Information Disclosure

#### T-I1 — Attacker reads another user's pantry, saved recipes, or meal plans

**Likelihood:** Medium — common in APIs with IDOR vulnerabilities  
**Impact:** High — privacy violation

**Mitigations in place:**
- Every queryset filtered by `user=request.user` — no queryset returns cross-user data
- 21 automated permission isolation tests verify this for every resource type — run in CI
- `get_object_or_404` always called with `user=request.user` filter — returns 404 not 403 to avoid confirming resource existence

**Residual risk:** Low. Belt-and-suspenders: code pattern + automated tests.

---

#### T-I2 — Engine API keys leaked via logs, error responses, or code

**Likelihood:** Low  
**Impact:** Critical — attacker can query engine directly, bypass rate limits

**Mitigations in place:**
- Keys stored only in `.env` and Render secrets — never committed to git
- `.gitignore` excludes `.env`
- `gitleaks` runs in pre-commit hooks and CI — blocks commits containing secrets
- Keys never appear in logs, error responses, or API responses
- Engine key format (`ffk_<40hex>`) gives gitleaks a specific pattern to catch

**Residual risk:** Low. Keys rotate every 90 days with 24-hour overlap.

---

#### T-I3 — User data exposed via verbose error messages

**Likelihood:** Medium  
**Impact:** Medium — internal paths, stack traces, DB schema revealed

**Mitigations in place:**
- `DEBUG = False` in production
- Custom exception handler returns structured error format — never raw tracebacks
- Sentry captures full errors server-side — client receives only `code` + `message`
- `ALLOWED_HOSTS` set to specific domains — rejects `Host` header injection

**Residual risk:** Low. Standard Django production hardening.

---

#### T-I4 — Database backup contains unencrypted sensitive data

**Likelihood:** Low  
**Impact:** High — full user data exposure if backup file is stolen

**Mitigations in place:**
- Passwords stored as Argon2id hashes — cannot be reversed
- Backup files compressed and should be stored off-server with access controls
- 35-day retention, then purged

**Residual risk:** Medium. **Off-server backup storage is not yet automated.** Currently backups exist only on the local disk. This must be resolved post-launch (copy nightly backup to encrypted object storage — S3/R2/Backblaze).

---

#### T-I5 — User ID or email sent to the engine

**Likelihood:** Low (code pattern issue, not an attack)  
**Impact:** High — violates the two-system rule, creates cross-system user tracking

**Mitigations in place:**
- `EngineClient` methods accept only food-related parameters — no user fields in the interface
- Engine search payload explicitly reviewed: only `ingredients`, `diet`, `mode`, `lang`, `limit`, `exclude`
- Code review requirement: any change to `apps/engine_client/client.py` must be reviewed for PII leakage

**Residual risk:** Low. Enforced by typed interface design.

---

### 3.5 Denial of Service

#### T-D1 — Attacker floods the search endpoint

**Likelihood:** High — search is the most expensive endpoint  
**Impact:** Medium — degrades service for all users

**Mitigations in place:**
- Rate limiting: anonymous 60/min, authenticated users 300/min, OTP 5/min
- Redis-backed rate limiter — consistent across workers
- Engine results cached in Redis (5 min TTL, keyed by input + diet + dataset_version) — repeated identical searches hit cache, not the engine
- Circuit breaker protects the engine from being overwhelmed by consumer traffic

**Residual risk:** Medium. A distributed attack from many IPs can overwhelm the rate limiter. Mitigation path: Cloudflare WAF rules (post-launch).

---

#### T-D2 — Engine outage takes down the consumer API

**Likelihood:** Medium — engine is a dependency for search and dish pages  
**Impact:** Medium — search degraded, but auth, pantry, billing all still work

**Mitigations in place:**
- Circuit breaker opens after 5 consecutive failures, half-opens after 30s
- Degraded mode: cached results served with `"engine_status": "degraded"` in response
- Saved recipes, meal plans, pantry all work without engine
- Incident tabletop completed 2026-10-31 — response procedure documented

**Residual risk:** Low for core features. Search is unavailable during full engine outage with empty cache.

---

#### T-D3 — OTP endpoint abused for SMS/cost flooding

**Likelihood:** Medium — phone OTP is a common abuse target  
**Impact:** Medium — cost (OTP delivery fees) + harassment of phone owners

**Mitigations in place:**
- OTP rate limit: 5 attempts per minute per IP (`THROTTLE_OTP`)
- OTP TTL: 5 minutes
- Max attempts before lockout enforced in `PhoneOTPView`

**Residual risk:** Low-Medium. Per-IP limiting can be bypassed with rotating IPs. Consider CAPTCHA on OTP at launch if abuse is seen.

---

### 3.6 Elevation of Privilege

#### T-E1 — Regular user accesses Plus-gated features without paying

**Likelihood:** Medium — common in billing systems  
**Impact:** Medium — revenue loss

**Mitigations in place:**
- `require_plus` decorator on all gated endpoints (meal plans, shopping lists, nutrition, offline sync)
- Entitlement check reads `Subscription.status` from DB on every request — not from the JWT
- Subscription status changes take effect immediately (no token re-issue needed)

**Residual risk:** Low. Entitlements are DB-checked, not claim-checked.

---

#### T-E2 — Regular user accesses Django admin

**Likelihood:** Low  
**Impact:** Critical — full system access

**Mitigations in place:**
- Admin at `/admin/` requires `is_staff = True`
- Staff 2FA mandatory (`django-two-factor-auth`) — TOTP or hardware key, no SMS/email codes
- Admin blocked from public internet in production — accessible only via Tailscale
- UFW firewall: port 22 (SSH) only on Tailscale interface — admin port 443 serves admin but Tailscale restricts who can reach the server shell

**Residual risk:** Low. Two-factor + network isolation.

---

#### T-E3 — Attacker SSH into the server directly from the internet

**Likelihood:** Very low (since 2026-10-31)  
**Impact:** Critical — full server access

**Mitigations in place:**
- UFW firewall: port 22 only allowed on `tailscale0` interface — public internet cannot reach SSH
- Tailscale requires device authentication + account membership (`dallah.dev` org)
- SSH key authentication only — no password SSH
- Confirmed live: firewall configured and tested 2026-10-31

**Residual risk:** Very low. Requires compromising a Tailscale-enrolled device.

---

## 4. Risk Summary

| ID | Threat | Likelihood | Impact | Residual Risk | Status |
|---|---|---|---|---|---|
| T-S1 | JWT forgery | Low | Critical | Low | ✅ Mitigated |
| T-S2 | Token replay | Medium | High | Low | ✅ Mitigated |
| T-S3 | Paystack webhook spoofing | Medium | Critical | Low | ✅ Mitigated |
| T-S4 | Engine impersonation | Very Low | High | Very Low | ✅ Mitigated |
| T-T1 | Allergen filter bypass | Low | Critical | Negligible | ✅ Mitigated |
| T-T2 | Payment amount tampering | Medium | High | Low | ✅ Mitigated |
| T-T3 | Submission tampering | Low | Medium | Low | ✅ Mitigated |
| T-R1 | Payment repudiation | Medium | Medium | Low | ✅ Mitigated |
| T-R2 | Moderation repudiation | Low | Medium | Low | ✅ Mitigated |
| T-I1 | Cross-user data access (IDOR) | Medium | High | Low | ✅ Mitigated |
| T-I2 | API key leakage | Low | Critical | Low | ✅ Mitigated |
| T-I3 | Verbose error disclosure | Medium | Medium | Low | ✅ Mitigated |
| T-I4 | Backup data exposure | Low | High | **Medium** | ⚠️ Off-server backup not automated |
| T-I5 | PII sent to engine | Low | High | Low | ✅ Mitigated |
| T-D1 | Search endpoint flood | High | Medium | Medium | ⚠️ Cloudflare WAF not yet configured |
| T-D2 | Engine outage cascade | Medium | Medium | Low | ✅ Mitigated |
| T-D3 | OTP abuse | Medium | Medium | Low-Medium | ⚠️ Consider CAPTCHA if abuse seen |
| T-E1 | Plus feature bypass | Medium | Medium | Low | ✅ Mitigated |
| T-E2 | Admin access | Low | Critical | Low | ✅ Mitigated |
| T-E3 | Direct SSH from internet | Very Low | Critical | Very Low | ✅ Mitigated (2026-10-31) |

---

## 5. Open Items (must resolve before or shortly after v1.0.0)

| # | Item | Priority | Owner |
|---|---|---|---|
| 1 | Automate off-server backups — nightly pg_dump → encrypted S3/R2/Backblaze | **High** | Engineering |
| 2 | Configure Cloudflare WAF rules for search endpoint flood protection | Medium | Engineering |
| 3 | Monitor OTP endpoint for abuse at launch — add CAPTCHA if needed | Low | Engineering |
| 4 | External penetration test — schedule for within 30 days of v1.0.0 | High | Engineering + External |
| 5 | Staff 2FA audit — verify all staff accounts have TOTP enrolled before launch | **High** | Dog254 |

---

## 6. What Is Out of Scope

- **Engine threats** — the engine has its own threat model; the consumer backend treats it as a trusted external service
- **Safaricom / Paystack infrastructure** — payment provider security is their responsibility
- **Android app** — client-side threats (rooted device, reverse engineering) are out of scope for this document
- **Physical security** — the staging server is a personal laptop; production Render infrastructure is managed by Render

---

## 7. Review Schedule

This document should be reviewed and updated:
- Before each major release
- After any security incident
- After significant architecture changes (new auth method, new payment provider, new third-party integration)
- At minimum, annually

Next review: **before v2.0.0** or **2027-11-01**, whichever comes first.
