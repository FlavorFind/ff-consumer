# Flavor Find — Consumer Backend (`ff-consumer`)

The Django/DRF backend that serves the Flavor Find website and Android app.
**Owns:** accounts, pantries, meal plans, saved recipes, subscriptions, community.
**Does not own:** food data — all dishes, ingredients, pairings come from the Recipe Engine via API.

---

## Quick start

**Prerequisites:** Python 3.12, Docker, Docker Compose.

```bash
# 1. Clone and enter the repo
git clone https://github.com/FlavorFind/ff-consumer.git
cd ff-consumer

# 2. Copy and fill in env vars
cp .env.example .env
# Edit .env — minimum required: ENGINE_API_KEY

# 3. Start all services (web + db + redis + worker)
make up

# 4. The API is now at http://localhost:8000
# Docs: http://localhost:8000/docs/
# Health: http://localhost:8000/v1/health/
```

---

## Development commands

```bash
make up            # Start all services (builds if needed)
make down          # Stop all services
make test          # Run tests
make test-cov      # Run tests with coverage report
make lint          # Run ruff linter
make format        # Run ruff formatter
make typecheck     # Run mypy type checking
make migrate       # Run database migrations
make makemigrations  # Create new migrations
make shell         # Django shell
make db-shell      # psql shell
```

---

## Project layout

```
apps/
  core/           Base models, middleware, exceptions, pagination
  accounts/       Users, auth (email+password, phone OTP), devices, consent
  profiles/       Language, household, diet tags, allergen exclusions
  engine_client/  Typed client for all Recipe Engine API calls
  billing/        Plans (Free/Plus), M-Pesa payments, entitlements
  api/            URL router, health, version endpoints
config/
  settings/       base, dev, test, prod
  urls.py         Root URL config
  celery.py       Celery application
docker/           Dockerfile, docker-compose.yml, entrypoint.sh
docs/             Architecture, sprint plan, runbooks
requirements/     base.txt, dev.txt, prod.txt
```

---

## Architecture in one line

```
App (website/Android) → Consumer Backend → Recipe Engine /v1/
```

The consumer backend **never reads the engine's database**. All food data comes from `https://engine.flavorfind.co.ke`.

---

## Key rules

1. **Never call the engine directly** from a view or model — all engine calls go through `apps/engine_client/client.py`
2. **Diet/allergens always sent** — every engine search call includes the user's diet restrictions. This is enforced in `SearchService`, not in views.
3. **Allergen disclaimer** required on every response mentioning dietary info: *"Allergen information is for guidance only. Always confirm with the kitchen before ordering."*
4. **Row-level scoping** — every queryset is filtered by `user=request.user`. Automated permission tests verify this.
5. **Staff 2FA mandatory** — no SMS or email codes for staff logins.

---

## Environment variables

See `.env.example` for the full list. Key ones:

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Django secret key |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `ENGINE_BASE_URL` | Yes | Engine URL (default: `https://engine.flavorfind.co.ke`) |
| `ENGINE_API_KEY` | Yes | Engine public key (`read:search`, `read:catalog` scopes) |
| `ENGINE_INTERNAL_KEY` | Yes | Engine internal key (`internal:curation` scope) |

Keys are created in the engine admin at `https://engine.flavorfind.co.ke/admin/`. Never commit them.

---

## Testing

```bash
make test-cov
```

Coverage gates:
- **85%** overall
- **95%** for `accounts`, `billing`, `engine_client`

---

## Staging

| Target | URL | Deploy |
|---|---|---|
| Render | Auto-deployed on push to `main` | `render.yaml` |
| Self-hosted | `mayday@100.96.139.83:/home/mayday/ff-consumer` | `deploy-staging.yml` |

Engine staging: `https://engine.flavorfind.co.ke` (Frankfurt, same server)

---

## Sprint plan

5 two-week iterations. See `docs/consumer-sprint-architecture.md` for the full plan.

| Iteration | Goal |
|---|---|
| 1 (current) | Foundations: auth, profiles, engine client |
| 2 | Search and pantry |
| 3 | Library, planner, offline sync |
| 4 | Community, billing, notifications |
| 5 | Hardening and v1.0.0 release |
