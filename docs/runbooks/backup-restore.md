# Runbook: Backup and Restore

**Service:** ff-consumer (Flavor Find Consumer Backend)  
**Owner:** FlavorFind engineering team  
**Last updated:** 2026-10-31

---

## Backup Strategy

| Target | Frequency | Retention | Storage |
|---|---|---|---|
| PostgreSQL DB (Render) | Daily (automated by Render) | 7 days (free tier) | Render managed |
| PostgreSQL DB (self-hosted) | Daily via cron | 35 days | `/var/backups/ff-consumer/` |
| Redis (queue state) | Not backed up — ephemeral | — | Celery tasks are idempotent |
| `.env` secrets | Manually after any change | Indefinitely | Secret manager only — never in git |

**Privacy note:** Backups contain personal user data (email, phone, payment records). Backup files must be stored encrypted and access must be logged. Retention is 35 days in line with our data retention policy.

---

## Automated Backup — Self-hosted Server

### Setup (run once)

```bash
# Create backup directory
sudo mkdir -p /var/backups/ff-consumer
sudo chown mayday:mayday /var/backups/ff-consumer

# Create backup script
cat > /home/mayday/backup-ff-consumer.sh << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/var/backups/ff-consumer"
DB_URL=$(grep DATABASE_URL /home/mayday/ff-consumer/.env | cut -d= -f2-)

# Dump database
pg_dump "$DB_URL" | gzip > "${BACKUP_DIR}/db_${DATE}.sql.gz"

# Remove backups older than 35 days
find "$BACKUP_DIR" -name "db_*.sql.gz" -mtime +35 -delete

echo "Backup completed: ${BACKUP_DIR}/db_${DATE}.sql.gz"
EOF

chmod +x /home/mayday/backup-ff-consumer.sh

# Add to cron (runs daily at 02:00 EAT = 23:00 UTC)
(crontab -l 2>/dev/null; echo "0 23 * * * /home/mayday/backup-ff-consumer.sh >> /var/log/ff-consumer/backup.log 2>&1") | crontab -
```

### Verify backups are running

```bash
ls -lh /var/backups/ff-consumer/
tail -20 /var/log/ff-consumer/backup.log
```

---

## Manual Backup

```bash
ssh -o StrictHostKeyChecking=no mayday@100.96.139.83

# Read DATABASE_URL from env
source /home/mayday/ff-consumer/.env

# Create backup with timestamp
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump "$DATABASE_URL" | gzip > "/var/backups/ff-consumer/manual_${DATE}.sql.gz"
echo "Backup saved: manual_${DATE}.sql.gz"
```

---

## Restore from Backup

### ⚠️ Warning

Restore replaces ALL current data with the backup snapshot. Any data created after the backup timestamp will be lost. Confirm with the team before restoring to production.

### Steps

```bash
ssh -o StrictHostKeyChecking=no mayday@100.96.139.83

# 1. List available backups
ls -lh /var/backups/ff-consumer/

# 2. Choose the backup file to restore (e.g. db_20261030_020000.sql.gz)
BACKUP_FILE="/var/backups/ff-consumer/db_20261030_020000.sql.gz"

# 3. Stop traffic — put gunicorn in maintenance mode
sudo systemctl stop gunicorn-ff-consumer

# 4. Read DATABASE_URL
source /home/mayday/ff-consumer/.env

# 5. Drop and recreate the database
# DANGER: this destroys all current data
psql "$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# 6. Restore from backup
gunzip -c "$BACKUP_FILE" | psql "$DATABASE_URL"

# 7. Run any pending migrations (should be none if backup is recent)
cd /home/mayday/ff-consumer
.venv/bin/python manage.py migrate --no-input

# 8. Restart gunicorn
sudo systemctl start gunicorn-ff-consumer

# 9. Verify
curl -s http://localhost:8001/v1/health/
```

### Restore on Render

1. Log in to [Render dashboard](https://dashboard.render.com).
2. Select database `flavorfind-consumer-db`.
3. Click **Backups** tab.
4. Select the backup to restore.
5. Click **Restore**.
6. After restore completes, trigger a manual deploy to re-run migrations if needed.

---

## Backup Restore Drill

Perform this drill before v1.0.0 launch to confirm the process works.

### Drill steps (use staging server — not production)

1. Create a test user and some pantry items on staging.
2. Take a manual backup.
3. Create more data (to simulate data that will be "lost" in the restore).
4. Restore from the backup taken in step 2.
5. Verify the test user exists with the pantry items from before step 3.
6. Verify data created in step 3 is gone.
7. Document in `docs/drills/backup-restore-<date>.md`:
   - Time taken
   - Any issues encountered
   - Recovery confirmed: yes/no

### Success criteria

- Restore completes without errors
- Data integrity verified (user exists, pantry items match)
- `GET /v1/health/` returns `{"status": "ok"}` after restore
- Time to restore: documented

---

## Data Retention Policy

| Data type | Retention | Basis |
|---|---|---|
| User account data | Until account deletion + 35-day grace period | User consent, GDPR-equivalent |
| Payment records | 7 years | KRA/financial regulation |
| Audit logs | 2 years | Security and compliance |
| Database backups | 35 days | Operational recovery window |
| Deleted account data (soft delete) | 35 days after `DELETE /me` | Grace period for recovery |

After the grace period, deleted accounts are purged by the `purge_user_data_after_grace_period` Celery task.
