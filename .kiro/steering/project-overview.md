# Flavor Find — Consumer Backend (ff-consumer)

## What this repo is

`ff-consumer` is the Django/DRF backend that serves the Flavor Find consumer website and Android app.
It owns everything about **people**: accounts, pantries, meal plans, saved recipes, subscriptions, community submissions.
It owns **nothing about food** — all food data comes from the Recipe Engine via API.

## Organisation and repos

- **GitHub org:** `FlavorFind`
- **This repo:** `FlavorFind/ff-consumer`
- **Engine repo:** `FlavorFind/ff-engine` (already complete and live)
- **Console repo:** `FlavorFind/ff-console` (internal test UI, lives inside ff-engine)

## The two-system rule

```
Consumer Backend  ──── X ──── Engine DB   (never)
Consumer Backend  ──────────► Engine API  (only route)
```

The backend calls the engine with two API keys:
1. **Public key** — scopes `read:search`, `read:catalog` — for all search, dish, ingredient, pairing, substitution, region calls
2. **Internal key** — scope `internal:curation` — only for submitting community recipes as drafts

The engine logs **what** was asked, never **who** asked. The backend must never send user IDs, emails, or device data to the engine.

## Stack (match the engine exactly — one toolchain, one team)

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Framework | Django 5.2.x + Django REST Framework 3.18.x |
| Database | PostgreSQL 16 (own DB, never shared with engine) |
| Cache / Queue broker | Redis 7 |
| Background tasks | Celery 5.4.0 + django-celery-beat |
| API docs | drf-spectacular 0.30.0 |
| Auth (users) | Argon2id passwords + phone OTP; JWT short-lived access + rotating refresh |
| Auth (staff) | Django sessions + django-two-factor-auth (mandatory, no SMS/email codes) |
| Payments | M-Pesa Daraja STK push |
| Staging | Render (Frankfurt region — same as engine for low latency) |
| CI/CD | GitHub Actions (same gates as engine) |
| Linting | ruff |
| Type checking | mypy |
| Testing | pytest + pytest-django |

## Staging server (self-hosted, Tailscale)

The engine runs on a self-hosted Lenovo ThinkPad reachable via Tailscale:

```
Host:     100.96.139.83  (Tailscale IP)
User:     mayday
SSH:      ssh -o StrictHostKeyChecking=no mayday@100.96.139.83
Engine:   /home/mayday/ff-engine
```

The consumer backend will also deploy to this server in addition to Render.
Deploy workflow pattern: Tailscale → SSH → git pull → pip install → migrate → restart gunicorn.

## Engine staging URL

```
https://engine.flavorfind.co.ke   (primary)
https://dev.engine.flavorfind.co.ke  (dev/staging alias)
```

Health check: `GET /v1/health/`
API docs: `https://engine.flavorfind.co.ke/docs/`
Dataset version: `GET /v1/meta/version/`

## Current engine state

- **Engine version:** 1.0.0
- **Dataset version:** 2026.10.0
- **Status:** Complete, all CI green, deployed to staging
- **881 ingredients** seeded, full East African dish coverage
- All engine endpoints documented in `engine-api-contract.md`
