# Runbook: Incident Response

**Service:** ff-consumer (Flavor Find Consumer Backend)  
**Owner:** FlavorFind engineering team  
**Last updated:** 2026-10-31

---

## Incident Severity Levels

| Level | Definition | Response time | Examples |
|---|---|---|---|
| **P1 — Critical** | Service down or data breach | Immediate (< 15 min) | Health check failing, database down, payment processing broken, user data exposed |
| **P2 — High** | Major feature broken, degraded performance | < 1 hour | Search returning wrong results, auth broken, Celery queue backed up |
| **P3 — Medium** | Feature partially broken, recoverable errors | < 4 hours | Email delivery failing, engine degraded (cache serving), non-critical endpoint errors |
| **P4 — Low** | Minor issues, cosmetic bugs | Next business day | Slow endpoint, typo in response, log noise |

---

## Incident Response Process

### 1. Detect

- Sentry alert fires
- Uptime monitor alerts (health check fails)
- User reports via support channel
- CI/CD pipeline fails post-deploy

### 2. Acknowledge

- Post in `#incidents` (or team channel): `"Investigating [symptom] since [time]. I'm on it — @oncall"`
- Set a status page message if user-facing

### 3. Assess Severity

Use the table above. If in doubt, treat as P2.

### 4. Contain

For P1 (service down): **roll back immediately** — see [rollback runbook](rollback.md).  
For P2 (wrong data / security issue): **disable the affected endpoint** while investigating:

```bash
# Emergency: return 503 for a specific endpoint by adding a flag in settings
# or deploy a hotfix that returns a safe error message
```

### 5. Investigate

Key investigation commands:

```bash
# --- Server logs ---
ssh mayday@100.96.139.83
sudo journalctl -u gunicorn-ff-consumer -n 200 --no-pager
tail -100 /var/log/ff-consumer/error.log

# --- Database ---
cd /home/mayday/ff-consumer
source .env
psql "$DATABASE_URL" -c "SELECT count(*), max(created_at) FROM accounts_user;"

# --- Celery queue depth ---
.venv/bin/celery -A config inspect active
.venv/bin/celery -A config inspect reserved

# --- Redis ---
redis-cli info stats | grep rejected
redis-cli info keyspace

# --- Engine health ---
curl -s https://engine.flavorfind.co.ke/v1/health/
```

### 6. Fix

- Write a hotfix on a branch: `fix/incident-<date>-<description>`
- All CI checks must pass
- Get 1 approval (P1: can self-approve with async notification to team)
- Deploy via normal pipeline or manual deploy (see [deploy runbook](deploy.md))

### 7. Verify

- Health check green
- Error rate back to baseline in Sentry
- Affected functionality confirmed working

### 8. Post-Incident

Within 24 hours, write a post-incident note in `docs/post-mortems/` using the template below.

---

## Scenario Playbooks

### Engine Down / Degraded

**Symptom:** `GET /v1/health/` returns `engine_status: degraded`. Search returns stale results.

**Response:**
1. Verify engine is down: `curl -s https://engine.flavorfind.co.ke/v1/health/`
2. Check engine server: `ssh mayday@100.96.139.83` → `sudo systemctl status gunicorn-ff-engine`
3. Consumer backend automatically serves cached results — no action needed for < 30 minutes.
4. If engine is down > 30 minutes: post status update to users.
5. Circuit breaker will auto-open after 5 failures and try half-open every 30 seconds.
6. To manually reset the circuit breaker (if needed):
   ```bash
   redis-cli DEL ffconsumer_engine:circuit_state ffconsumer_engine:circuit_failures
   ```
7. When engine recovers: circuit breaker closes automatically on next successful call.

**SLA:** Consumer continues serving cached data for up to 1 hour without user impact.

---

### Payment Callback Failure

**Symptom:** Users paying via M-Pesa/Paystack report subscription not activating.

**Response:**
1. Check Paystack dashboard for webhook delivery status.
2. Check callback endpoint logs:
   ```bash
   grep "mpesa_callback\|paystack.*webhook" /var/log/ff-consumer/access.log | tail -50
   ```
3. Check for signature verification failures in Sentry.
4. Check `billing_payment` table for pending payments:
   ```bash
   psql "$DATABASE_URL" -c "SELECT id, user_id, amount_kes, status, created_at FROM billing_payment WHERE status = 'pending' ORDER BY created_at DESC LIMIT 20;"
   ```
5. If payment is confirmed on Paystack but pending in DB: **do not manually activate** — investigate the webhook.
6. Re-deliver the webhook from Paystack dashboard if safe to do so (idempotency key will prevent double-activation).
7. If re-delivery is not possible, manually verify the transaction and update with an audit log entry.

**NEVER trust a callback amount — always re-verify against the expected plan price.**

---

### User Data Export / Deletion Request (GDPR-equivalent)

**Symptom:** User requests data export or account deletion via support.

**Response — Export:**
1. Direct user to `GET /me/export` endpoint (authenticated). Returns JSON of all their data.
2. If the endpoint is broken, run manually:
   ```bash
   cd /home/mayday/ff-consumer
   .venv/bin/python manage.py shell -c "
   from apps.accounts.views import _build_user_export
   from apps.accounts.models import CustomUser
   u = CustomUser.objects.get(email='user@example.com')
   import json; print(json.dumps(_build_user_export(u), default=str, indent=2))
   "
   ```

**Response — Deletion:**
1. User can self-delete via `DELETE /me`. This soft-deletes the account.
2. Purge happens automatically 35 days later via `purge_user_data_after_grace_period` Celery task.
3. If manual deletion is required: confirm in audit log, then delete (see accounts/tasks.py for purge logic).

---

### Security Incident / Suspected Data Breach

1. **Contain immediately:** revoke all active JWT tokens for affected users, rotate `SECRET_KEY`.
2. **Preserve evidence:** take a DB snapshot before any cleanup.
3. **Notify:** inform team lead within 15 minutes.
4. **Assess scope:** which users are affected? What data was exposed?
5. **Notify affected users:** within 72 hours if personal data was exposed (regulatory requirement).
6. **Rotate secrets:** `SECRET_KEY`, `ENGINE_API_KEY`, `ENGINE_INTERNAL_KEY`, `PAYSTACK_SECRET_KEY`.
7. **File post-mortem** within 24 hours.

---

### High Error Rate After Deploy

1. Check Sentry for error patterns.
2. Check `GET /v1/health/` — is it still returning 200?
3. If error rate > 5% on any endpoint: **roll back** (see [rollback runbook](rollback.md)).
4. If error rate is in a non-critical endpoint: keep running, open a P2 incident, fix and deploy hotfix.

---

## Post-Mortem Template

File as `docs/post-mortems/YYYY-MM-DD-<short-description>.md`:

```markdown
# Post-Mortem: <Title>

**Date:** YYYY-MM-DD  
**Duration:** X hours  
**Severity:** P1/P2/P3  
**Author:** <name>

## Summary
One paragraph: what happened, what broke, what the user impact was.

## Timeline (EAT)
- HH:MM — Alert fired / incident detected
- HH:MM — Engineer acknowledged
- HH:MM — Root cause identified
- HH:MM — Fix deployed
- HH:MM — Recovery confirmed

## Root Cause
Technical explanation of what went wrong.

## Impact
- Users affected: N
- Duration of impact: X minutes
- Data loss: none / describe

## Fix
What was done to resolve the incident.

## Action Items
- [ ] What to prevent recurrence — assigned to @person, due date
- [ ] Monitoring improvement
- [ ] Runbook update if needed
```

---

## Contacts

| Role | Contact |
|---|---|
| Engineering lead | Dog254 (GitHub) |
| Staging server | `ssh mayday@100.96.139.83` |
| Engine health | `https://engine.flavorfind.co.ke/v1/health/` |
| Sentry | Project: ff-consumer |
| Paystack dashboard | `https://dashboard.paystack.com` |
| Render dashboard | `https://dashboard.render.com` |
