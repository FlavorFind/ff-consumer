# Runbook: Deploy

**Service:** ff-consumer (Flavor Find Consumer Backend)  
**Owner:** FlavorFind engineering team  
**Last updated:** 2026-10-31

---

## Overview

ff-consumer has two deployment targets that are updated on every push to `main`:

| Target | Trigger | URL |
|---|---|---|
| Render (Frankfurt) | Auto-deploy via Render GitHub integration | `https://consumer.flavorfind.co.ke` |
| Self-hosted (Tailscale) | GitHub Actions `deploy-staging.yml` | `http://100.96.139.83` |

Both deployments are triggered automatically when all CI checks pass on `main`.

---

## Normal Deploy (automated)

1. Open a PR against `main`.
2. CI runs: lint → SAST → dependency audit → tests → migration check → schema validation.
3. Get 1 approval from a non-author.
4. Merge. Both deployments start automatically.
5. Monitor health at `GET /v1/health/` — expect `{"status": "ok"}` within 3 minutes.

**CI must be green before merging. No exceptions.**

---

## Manual Deploy — Self-hosted Server

Use this when the GitHub Actions deploy fails or you need to force a redeploy.

### Prerequisites
- Tailscale connected on your machine
- SSH access: `ssh -o StrictHostKeyChecking=no mayday@100.96.139.83`

### Steps

```bash
# 1. Connect to server
ssh -o StrictHostKeyChecking=no mayday@100.96.139.83

# 2. Navigate to project
cd /home/mayday/ff-consumer

# 3. Pull latest code
git fetch origin
git checkout main
git reset --hard origin/main

# 4. Install dependencies
.venv/bin/pip install -q -r requirements/prod.txt --prefer-binary

# 5. Run migrations
.venv/bin/python manage.py migrate --no-input

# 6. Collect static files
.venv/bin/python manage.py collectstatic --no-input --clear

# 7. Reload gunicorn (zero-downtime reload)
sudo systemctl reload gunicorn-ff-consumer

# 8. Verify health
curl -s http://localhost:8001/v1/health/ | python3 -m json.tool
```

Expected health response:
```json
{
    "status": "ok",
    "version": "1.x.x",
    "engine_status": "ok",
    "dataset_version": "2026.10.0"
}
```

### Smoke tests (run from server, not from CI runner — Cloudflare blocks external runners)

```bash
cd /home/mayday/ff-consumer
.venv/bin/python manage.py test_smoke  # if smoke test command exists
# or manually:
curl -sf http://localhost:8001/v1/health/ && echo "health OK"
curl -sf http://localhost:8001/v1/meta/version/ && echo "version OK"
```

---

## Manual Deploy — Render

1. Log in to [Render dashboard](https://dashboard.render.com).
2. Select service `ff-consumer`.
3. Click **Manual Deploy → Deploy latest commit**.
4. Watch the deploy log — it should complete in under 5 minutes.
5. Verify health at `https://consumer.flavorfind.co.ke/v1/health/`.

---

## Environment Variables

Critical env vars that must be set in both Render and the self-hosted server:

| Variable | Where to set | Notes |
|---|---|---|
| `SECRET_KEY` | Render: auto-generated; server: `.env` | Rotate if compromised |
| `DATABASE_URL` | Render: linked DB; server: `.env` | Never share between envs |
| `REDIS_URL` | Render: env var; server: `.env` | |
| `ENGINE_API_KEY` | Render: manual; server: `.env` | Rotate every 90 days |
| `ENGINE_INTERNAL_KEY` | Render: manual; server: `.env` | Rotate every 90 days |
| `PAYSTACK_SECRET_KEY` | Render: manual; server: `.env` | |
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` | |

**Never commit secrets to git. Never log secrets. `ENGINE_API_KEY` and `ENGINE_INTERNAL_KEY` must come from the secret manager, not from code.**

---

## Post-deploy Checks

- [ ] `GET /v1/health/` returns `{"status": "ok"}`
- [ ] `GET /v1/meta/version/` returns engine `dataset_version`
- [ ] `POST /v1/auth/register/` creates a user (staging only — use a test email)
- [ ] Admin login works at `/admin/` (2FA required)
- [ ] Celery workers are running: `sudo systemctl status celery-ff-consumer`
- [ ] Celery beat is running: `sudo systemctl status celerybeat-ff-consumer`

---

## Gunicorn Configuration

```
# /etc/systemd/system/gunicorn-ff-consumer.service
[Unit]
Description=ff-consumer gunicorn daemon
After=network.target

[Service]
User=mayday
Group=www-data
WorkingDirectory=/home/mayday/ff-consumer
EnvironmentFile=/home/mayday/ff-consumer/.env
ExecStart=/home/mayday/ff-consumer/.venv/bin/gunicorn config.wsgi:application \
    --bind 127.0.0.1:8001 \
    --workers 2 \
    --timeout 120 \
    --access-logfile /var/log/ff-consumer/access.log \
    --error-logfile /var/log/ff-consumer/error.log
ExecReload=/bin/kill -s HUP $MAINPID
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

---

## Known Deploy Issues

| Symptom | Likely cause | Fix |
|---|---|---|
| `502 Bad Gateway` after deploy | Gunicorn failed to start | Check `/var/log/ff-consumer/error.log` |
| `django.db.utils.OperationalError` | Missing migration | Run `python manage.py migrate` manually |
| Health returns `engine_status: degraded` | Engine unreachable | Check engine health; consumer still serves cached data |
| Static files 404 | `collectstatic` skipped | Run `python manage.py collectstatic --no-input` |
| Celery tasks not processing | Worker not running | `sudo systemctl restart celery-ff-consumer` |
