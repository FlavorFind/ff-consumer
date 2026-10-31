# Runbook: Rollback

**Service:** ff-consumer (Flavor Find Consumer Backend)  
**Owner:** FlavorFind engineering team  
**Last updated:** 2026-10-31

---

## When to Roll Back

Roll back immediately if any of these are true after a deploy:

- `GET /v1/health/` returns non-200 for more than 1 minute
- Error rate on any endpoint exceeds 5% (check Sentry)
- A data integrity issue is detected (missing or corrupted user data)
- A security vulnerability is discovered in the deployed code
- Search p95 latency degrades beyond 500 ms

**Do not wait for a fix. Roll back first, investigate second.**

---

## Rollback Decision Tree

```
Is CI/CD broken (no green build to roll back to)?
  YES → Manual rollback (steps below) using last known good commit
  NO  → Use automated rollback (Render) or git rollback

Did the deploy include a database migration?
  YES → Follow "Rollback with Migration" section — coordinate carefully
  NO  → Standard rollback, no DB concern
```

---

## Standard Rollback — Render

1. Log in to [Render dashboard](https://dashboard.render.com).
2. Select service `ff-consumer`.
3. Click **Deploys** tab.
4. Find the last successful deploy (green checkmark).
5. Click **Rollback to this deploy**.
6. Wait for deploy to complete (~3 minutes).
7. Verify: `GET https://consumer.flavorfind.co.ke/v1/health/`

---

## Standard Rollback — Self-hosted Server

```bash
# 1. SSH to server
ssh -o StrictHostKeyChecking=no mayday@100.96.139.83
cd /home/mayday/ff-consumer

# 2. Find the last good commit
git log --oneline -10

# 3. Checkout that commit (replace <SHA> with the target)
git checkout <SHA>

# 4. Re-install dependencies for that version
.venv/bin/pip install -q -r requirements/prod.txt --prefer-binary

# 5. Reload gunicorn
sudo systemctl reload gunicorn-ff-consumer

# 6. Verify health
curl -s http://localhost:8001/v1/health/
```

After rollback is verified, return main to the last good state:
```bash
# On your local machine
git revert HEAD  # if the bad commit is a single commit
# or
git checkout main
git reset --hard <last_good_SHA>
git push --force-with-lease origin main  # requires explicit approval
```

---

## Rollback with Migration (Backward Migration)

Only attempt this if the migration is reversible. Check the migration file first:
- If it only adds nullable columns or new tables → safely reversible
- If it drops columns, renames columns, or removes data → **not safely reversible** — contact the team lead before proceeding

### Steps for reversible migration rollback:

```bash
ssh -o StrictHostKeyChecking=no mayday@100.96.139.83
cd /home/mayday/ff-consumer

# 1. Check current migration state
.venv/bin/python manage.py showmigrations

# 2. Revert the specific migration (replace app and name)
# Example: revert billing 0003_add_checkout_url
.venv/bin/python manage.py migrate billing 0002  # the migration BEFORE the one to revert

# 3. Checkout the previous code version
git checkout <last_good_SHA>

# 4. Re-install dependencies
.venv/bin/pip install -q -r requirements/prod.txt --prefer-binary

# 5. Reload gunicorn
sudo systemctl reload gunicorn-ff-consumer

# 6. Verify
curl -s http://localhost:8001/v1/health/
```

### If migration is NOT reversible:

1. Do NOT run `migrate --reverse`. Data loss is permanent.
2. Keep the new code running on the new schema.
3. Write a hotfix that resolves the issue without rolling back the schema.
4. Deploy the hotfix through the normal CI/CD pipeline.

---

## Post-Rollback Checklist

- [ ] `GET /v1/health/` returns `{"status": "ok"}`
- [ ] Error rate back to baseline in Sentry
- [ ] Celery workers processing tasks (check Flower or `sudo systemctl status celery-ff-consumer`)
- [ ] Post incident note written in `#incidents` Slack channel (or equivalent)
- [ ] Root cause identified before re-deploying the broken change

---

## Rollback Drill (Practice)

Perform this drill before v1.0.0 launch. Steps:

1. Deploy a deliberately broken build (e.g. a view that always returns 500).
2. Verify the break (`GET /v1/health/` fails or Sentry shows errors).
3. Execute the standard rollback procedure above.
4. Verify recovery.
5. Document time-to-recovery in `docs/drills/rollback-<date>.md`.

Target time-to-recovery: **under 5 minutes** for a standard rollback.
