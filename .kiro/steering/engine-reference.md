# Engine Reference — For Consumer Backend Developers

This file documents the engine's internal structure so consumer backend developers
understand how it works without needing to read the engine codebase.

## Engine Codebase Location

```
Server:  mayday@100.96.139.83  (Tailscale IP, ssh -o StrictHostKeyChecking=no)
Path:    /home/mayday/ff-engine
Venv:    /home/mayday/ff-engine/.venv
```

## Engine Django Apps

```
apps/core          — Base models (TimeStampedModel, StatusMixin), middleware, pagination, exceptions
apps/accounts      — Staff user model (CustomUser), admin with 2FA
apps/ingredients   — Ingredient model, aliases, resolve endpoint
apps/dishes        — Dish model, required/optional ingredients, search arrays, pairings, substitutions
apps/regions       — Region model (47 counties + neighbouring countries)
apps/dietary       — Dietary tags, allergen tags, derived tag signals
apps/pairings      — Pairing graph between dishes
apps/substitutions — Substitution rules between ingredients
apps/nutrition     — Nutrition estimates per dish (labelled as estimates)
apps/search        — Search engine: by-ingredients endpoint, scoring, tiering, caching
apps/curation      — Data management: seed commands, community submissions intake, dataset diff
apps/clients       — API clients, API keys (SHA-256 hashed), scopes, rate limiting, metering
apps/api           — URL routing, health/version views
```

## Engine Base Model

All engine models inherit `TimeStampedModel`:
```python
class TimeStampedModel(Model):
    id = UUIDField(primary_key=True, default=uuid4, editable=False)
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
```

Most models also have `status` (draft|reviewed|verified|archived) via `StatusMixin`.

## Engine API Key System

Keys are never stored in plain text. Only SHA-256 hash + first 8 chars (prefix) are stored.
Format: `ffk_<40 hex chars>`

When the consumer backend calls the engine:
1. Engine extracts key from `X-API-Key` header
2. Takes first 8 chars → DB lookup by prefix (indexed)
3. Hashes full key → compares to stored hash
4. Checks scopes on the key match the endpoint's required scope

Scopes:
- `read:search` — required for `POST /v1/search/by-ingredients`
- `read:catalog` — required for dishes, ingredients, regions, pairings, substitutions
- `internal:curation` — required for `POST /v1/internal/submissions/`

Rate limit is per-key, default 60 req/min.

## Engine Search Response — Tier Meanings

| Tier | Meaning |
|---|---|
| `exact` | All required ingredients are in the user's pantry |
| `can_make` | All required ingredients present when staples (oil, salt, water) are assumed |
| `almost` | 1–2 required ingredients missing (only returned in `explore` mode) |

The consumer backend should:
- Show `exact` first as "Cook now"
- Show `can_make` as "Cook now (needs staples)"
- Show `almost` as "Almost there — missing X" (explore mode only)
- Never show `almost` in strict mode results

## Engine Dataset Version

Format: `YYYY.MM.patch` e.g. `2026.10.0`
Current: `2026.10.0`

This version changes whenever dish data, ingredients, or aliases are updated.
The consumer backend must:
1. Fetch it on startup from `GET /v1/meta/version/`
2. Cache it in Redis for 1 hour
3. Use it as part of all engine response cache keys
4. On version change: flush engine caches, flag saved recipes for drift check

## Engine Settings Reference (for matching the consumer settings)

Key settings to replicate in `ff-consumer/config/settings/base.py`:

```python
# Same timezone
TIME_ZONE = "Africa/Nairobi"

# Same cache key pattern (use different prefix)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "ffconsumer",   # engine uses "ffengine"
        "TIMEOUT": 300,
    }
}

# Same Celery timezone
CELERY_TIMEZONE = "Africa/Nairobi"

# Same logging structure (JSON formatter + request ID filter)
# Same security headers middleware pattern
# Same DRF exception handler → apps.core.exceptions.custom_exception_handler
```

## Engine Requirements (exact versions to match in consumer)

```
Django==5.2.17
djangorestframework==3.18.2
django-environ==0.11.2
psycopg2-binary==2.9.13
redis==5.1.1
hiredis==3.0.0
celery==5.4.0
django-celery-beat==2.9.0
django-celery-results==2.5.1
drf-spectacular==0.30.0
django-filter==24.3
djangorestframework-camel-case==1.4.2
django-cors-headers==4.4.0
sentry-sdk==2.17.0
django-otp==1.7.5
django-two-factor-auth==1.18.1
qrcode==8.2
Pillow==13.0.0
python-slugify==8.0.4
whitenoise==6.8.2
gunicorn==23.0.0
```

Additional packages needed in consumer (not in engine):
```
# Auth
djangorestframework-simplejwt==5.3.x   # JWT for end-user tokens
argon2-cffi==23.x                       # Argon2id password hashing

# Payments
# M-Pesa Daraja — use python-daraja or requests directly (no pinned library yet)

# Phone
# phonenumbers library for phone number validation/formatting
```

## Engine CI/CD Gates (replicate exactly)

From `.github/workflows/ci.yml`:

```yaml
jobs:
  lint:         ruff check . && ruff format --check .
  sast:         bandit -r apps/ -ll --skip B101,B106,B108,B311 -x <test dirs>
  dependency:   pip-audit -r requirements/base.txt -r requirements/prod.txt
  tests:        pytest with real Postgres + Redis, coverage gate
  migration:    python manage.py migrate --check
  schema:       drf-spectacular --validate
```

Coverage gates for consumer backend (from architecture doc):
- Overall: 85%
- `accounts`, `billing`, `engine_client`: 95%

## Engine Deploy Workflow (pattern for consumer)

```yaml
# From deploy-staging.yml
1. Connect to Tailscale (authkey from secrets)
2. SSH to mayday@100.96.139.83
3. cd /home/mayday/ff-engine
4. git fetch && git checkout main && git reset --hard origin/main
5. .venv/bin/pip install -q -r requirements/prod.txt --prefer-binary
6. python manage.py migrate --no-input
7. python manage.py collectstatic --no-input
8. sudo systemctl reload gunicorn-ff-engine  (or equivalent)
9. Run smoke tests from the server itself (not GitHub runners — Cloudflare blocks them)
```

For the consumer backend, the path will be `/home/mayday/ff-consumer`.

## Engine render.yaml Pattern (for consumer render.yaml)

```yaml
services:
  - type: web
    name: ff-consumer
    runtime: python
    region: frankfurt          # Same region as engine for low latency
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
        sync: false              # Set manually in Render dashboard
      - key: ENGINE_INTERNAL_KEY
        sync: false              # Set manually in Render dashboard

databases:
  - name: flavorfind-consumer-db
    databaseName: flavorfind_consumer_db
    plan: free
    region: frankfurt
```

## Engine Dockerfile Pattern

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && rm -rf /var/lib/apt/lists/*
COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/prod.txt
COPY . .
RUN python manage.py collectstatic --no-input
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
```

## Makefile Targets to Replicate

```makefile
up:        docker compose up --build
down:      docker compose down
test:      docker compose exec web pytest --tb=short -q
test-cov:  docker compose exec web pytest --cov=apps --cov-report=term-missing
lint:      docker compose exec web ruff check .
format:    docker compose exec web ruff format .
typecheck: docker compose exec web mypy apps/
migrate:   docker compose exec web python manage.py migrate
shell:     docker compose exec web python manage.py shell
```

## pyproject.toml Tools Config (copy from engine)

```toml
[tool.ruff]
target-version = "py312"
line-length = 100
exclude = [".git", ".venv", "__pycache__", "*/migrations/*"]

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "UP"]
ignore = ["E501"]

[tool.ruff.lint.isort]
known-first-party = ["apps", "config"]

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings.test"
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "--tb=short -q"

[tool.mypy]
python_version = "3.12"
ignore_missing_imports = true
plugins = ["mypy_django_plugin.main"]

[tool.django-stubs]
django_settings_module = "config.settings.dev"

[tool.coverage.run]
source = ["apps"]
omit = ["*/migrations/*", "*/tests/*"]
```

## Security Model from Engine (apply to consumer with additions)

Engine security:
- Staff 2FA mandatory (TOTP/hardware key — no SMS)
- API keys hashed (SHA-256), never stored plain
- RequestIDMiddleware on every request
- SecurityHeadersMiddleware (HSTS, X-Frame-Options, etc.)
- Append-only audit log
- Signed images (Docker), SBOM, Actions pinned by commit hash
- Rate limiting per key via `ApiKeyRateThrottle`

Consumer additions:
- End-user passwords: Argon2id (add `argon2-cffi` and set `PASSWORD_HASHERS`)
- JWT tokens: short-lived access (15 min) + rotating refresh (30 days)
- M-Pesa callback: verify source IP + signature before processing
- Field-level encryption for phone numbers
- GDPR-style: consent records, export endpoint, deletion endpoint, 35-day backup retention
- Row-level security: every queryset filtered by `user=request.user`
- Permission tests: automated test that tries to read another user's data (must fail)
