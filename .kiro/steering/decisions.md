# Decisions and Context

This file captures decisions made before the first line of code was written.
New decisions should be appended here with a date.

---

## 2026-10-30 — Project kickoff

### What is done (engine)
The Recipe Engine (`FlavorFind/ff-engine`) is **complete and live on staging**.
- Version: 1.0.0, dataset version: 2026.10.0
- 881 ingredients seeded, all East African dishes covered
- All CI checks passing, deployed to self-hosted server (`mayday@100.96.139.83`) and Render
- Engine URL: `https://engine.flavorfind.co.ke`
- Engine admin: `https://engine.flavorfind.co.ke/admin/` (staff 2FA required)
- Engine docs: `https://engine.flavorfind.co.ke/docs/`
- Engine internal console: `https://engine.flavorfind.co.ke/console/` (staff only)

The consumer backend calls the engine as a client. It does NOT share the engine's database.

### Stack decisions
- **Language:** Python 3.12 (match engine)
- **Framework:** Django 5.2.x + DRF 3.18.x (match engine)
- **Database:** PostgreSQL 16 — own separate database
- **Cache/broker:** Redis 7
- **Staging platform:** Render (Frankfurt region — same as engine for low latency)
- **Self-hosted staging:** same server as engine, path `/home/mayday/ff-consumer`

### Product decisions
- **Login methods:** email + password AND phone OTP (both at launch)
- **Public access:** search, dish pages, regions, stories accessible without login; personalisation requires auth
- **Free tier:** search is free and unlimited; Plus gates meal plans, nutrition details, offline sync, budget mode, unlimited saves
- **Plus price:** KES 199/month
- **Payment method:** M-Pesa Daraja STK push only at launch
- **Shopping list prices:** engine cost estimates only (no external price source) for v1
- **One team:** consumer backend and engine same team, same toolchain, same standards

### Decisions still open (resolve in Week 1)
- Plus trial length: 14 days or 30 days?
- Moderation staffing: who reviews community submissions? what's the turnaround SLA?
- Taste of 47 counties: who writes the editorial stories? which counties launch first (pick 5–10)?
- Minimum Android app version to support at launch

---

## Key contacts and accounts

- **GitHub org:** FlavorFind
- **Engine repo owner / admin:** Dog254 (GitHub account)
- **Staging server user:** mayday
- **Staging server IP (Tailscale):** 100.96.139.83
- **Timezone for all scheduling:** Africa/Nairobi (EAT, UTC+3)

---

## Architecture constraints (non-negotiable)

1. The backend never reads the engine database — API only
2. The backend never sends user IDs or emails to the engine
3. Diet/allergen exclusions MUST be sent on every search — no exceptions
4. Staff 2FA is mandatory — no SMS or email codes for staff
5. Argon2id for all user passwords
6. M-Pesa callback amount must be re-verified server-side — never trust the callback
7. Every row scoped to its owner — automated permission tests must verify this
8. Allergen text on every response that mentions dietary info: "Allergen information is for guidance only. Always confirm with the kitchen."
9. Audit log is append-only and shipped externally
10. No food tables in the consumer database — food lives in the engine

---

## Engine API key management

Two keys needed:
1. `ENGINE_API_KEY` — scopes: `read:search`, `read:catalog` — stored in secret manager as `ENGINE_API_KEY`
2. `ENGINE_INTERNAL_KEY` — scope: `internal:curation` — stored as `ENGINE_INTERNAL_KEY`

Keys are created in the engine admin at `https://engine.flavorfind.co.ke/admin/`.
The engine admin creates an `ApiClient` of type "internal" and generates a key.
Only the prefix (first 8 chars) is shown after creation — store the full key immediately in the secret manager.

Keys rotate every 90 days with overlap (old key stays valid 24h after new key is activated).

---

## CI/CD pattern (copy from engine)

Repository: `FlavorFind/ff-consumer`
Branch protection on `main`:
- Require PR + 1 approval (non-author)
- Require all CI checks to pass
- No direct push to main
- Signed commits

GitHub Actions secrets needed:
- `TAILSCALE_AUTHKEY` — for deploy workflow
- `DEPLOY_HOST` — `100.96.139.83`
- `DEPLOY_USER` — `mayday`
- `DEPLOY_SSH_KEY` — SSH private key for mayday
- `ENGINE_API_KEY` — for contract test job
- `ENGINE_INTERNAL_KEY` — for contract test job

---

## Render setup

1. Connect `FlavorFind/ff-consumer` repo to Render
2. Create web service + PostgreSQL (free tier, Frankfurt)
3. Add Redis (use Render Redis or set `REDIS_URL` env var pointing to Redis Cloud free tier)
4. Set `ENGINE_API_KEY` and `ENGINE_INTERNAL_KEY` manually in Render dashboard (not in render.yaml)
5. Health check path: `/v1/health/`
6. Auto-deploy on push to `main` (after CI passes)
