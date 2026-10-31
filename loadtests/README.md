# Load Tests — ff-consumer

Load tests for the Flavor Find Consumer Backend using [k6](https://k6.io).

## Sprint Exit Criteria

| Test | Criterion | Script |
|---|---|---|
| Peak load | Search p95 < 250ms at 50 req/s | `search.js` |
| Soak test | 2-hour sustained load, no degradation | `soak.js` |
| Baseline | Health check p95 < 100ms | `health.js` |

---

## Setup

### 1. Install k6

```bash
sudo gpg --no-default-keyring \
  --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 \
  --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69

echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/k6.list

sudo apt-get update && sudo apt-get install -y k6
```

### 2. Create a load test user on staging

The search test logs in as a real user to get a JWT. Create this account once:

```bash
curl -s -X POST https://consumer.flavorfind.co.ke/v1/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "loadtest@flavorfind.co.ke",
    "password": "LoadTest!2026",
    "username": "loadtestuser"
  }'
```

Then verify the email (check Django admin or use the verification endpoint).

### 3. Set environment variables

```bash
export BASE_URL=https://consumer.flavorfind.co.ke   # or http://100.96.139.83 for self-hosted
export TEST_EMAIL=loadtest@flavorfind.co.ke
export TEST_PASSWORD=LoadTest!2026
```

---

## Running Tests

### Baseline — health check (run this first)

```bash
k6 run loadtests/health.js
```

Expected: all checks pass, p95 < 100ms.

### Peak load — search at 50 req/s (~4 minutes)

```bash
k6 run loadtests/search.js
```

Or with explicit env vars:
```bash
BASE_URL=https://consumer.flavorfind.co.ke \
TEST_EMAIL=loadtest@flavorfind.co.ke \
TEST_PASSWORD=LoadTest!2026 \
k6 run loadtests/search.js
```

**Pass criterion:** `✓ http_req_duration{endpoint:search} p(95)<250` in the output.

To save results as JSON:
```bash
mkdir -p loadtests/results
k6 run loadtests/search.js --out json=loadtests/results/search-$(date +%Y%m%d-%H%M).json
```

### Soak test — 2 hours (run in a tmux session)

```bash
tmux new -s soak
mkdir -p loadtests/results
k6 run loadtests/soak.js --out json=loadtests/results/soak-$(date +%Y%m%d).json
# Ctrl+B then D to detach; tmux attach -t soak to re-attach
```

---

## Interpreting Results

k6 outputs a summary at the end. Key lines to check:

```
✓ http_req_duration{endpoint:search}  p(95)=183.2ms   ← must be < 250ms
✓ http_req_failed                     rate=0.00%       ← must be < 1%
✓ search_errors                       0                ← must be 0 (or < 5)
```

If the threshold line shows `✗` instead of `✓`, the test **failed**.

### Common failure causes

| Symptom | Likely cause | Fix |
|---|---|---|
| p95 > 250ms | Engine too slow or no Redis cache | Check engine health; verify Redis is running |
| High error rate | Engine circuit breaker open | Check `/v1/health/` for `engine_status: degraded` |
| 401 errors after ramp-up | JWT expired during long run | Refresh token logic — soak test may need token refresh |
| p95 increases over time (soak) | Memory or connection leak | Check gunicorn worker memory, DB connection pool |

---

## Recording Results

After each test run, save the result in `docs/drills/`:

```bash
# Example result file
cat > docs/drills/load-test-2026-10-31.md << 'EOF'
# Load Test Results — 2026-10-31

## Search (50 req/s peak)
- p50: XXms
- p95: XXms  ← PASS/FAIL vs 250ms
- p99: XXms
- Error rate: X%
- Duration: 4m

## Notes
...
EOF
```

---

## Files

| File | Purpose |
|---|---|
| `config.js` | Shared config, thresholds, helpers |
| `auth_setup.js` | Login helper, shared by other scripts |
| `health.js` | Baseline health check load test |
| `search.js` | Peak load test — the sprint exit criterion test |
| `soak.js` | 2-hour soak test |
| `results/` | JSON output files (gitignored) |
