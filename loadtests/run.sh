#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run.sh — convenience wrapper for ff-consumer load tests
#
# Usage:
#   ./loadtests/run.sh health         — baseline health check
#   ./loadtests/run.sh search         — peak load test (exit criterion)
#   ./loadtests/run.sh soak           — 2-hour soak test
#   ./loadtests/run.sh auth           — verify login only
#
# Environment (override as needed):
#   BASE_URL      — default: https://consumer.flavorfind.co.ke
#   TEST_EMAIL    — default: loadtest@flavorfind.co.ke
#   TEST_PASSWORD — default: LoadTest!2026
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
mkdir -p "$RESULTS_DIR"

export BASE_URL="${BASE_URL:-https://consumer.flavorfind.co.ke}"
export TEST_EMAIL="${TEST_EMAIL:-loadtest@flavorfind.co.ke}"
export TEST_PASSWORD="${TEST_PASSWORD:-LoadTest!2026}"

if ! command -v k6 &>/dev/null; then
  echo "ERROR: k6 is not installed."
  echo "Install with:"
  echo "  sudo apt-get install -y k6"
  echo "  (see loadtests/README.md for full setup)"
  exit 1
fi

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
TEST="${1:-help}"

case "$TEST" in
  health)
    echo "Running health baseline against $BASE_URL ..."
    k6 run "${SCRIPT_DIR}/health.js" \
      --out "json=${RESULTS_DIR}/health-${TIMESTAMP}.json"
    ;;
  search)
    echo "Running search peak load test (50 req/s) against $BASE_URL ..."
    echo "Exit criterion: p95 < 250ms"
    k6 run "${SCRIPT_DIR}/search.js" \
      --out "json=${RESULTS_DIR}/search-${TIMESTAMP}.json"
    ;;
  soak)
    echo "Running 2-hour soak test against $BASE_URL ..."
    echo "Consider running this in a tmux session."
    k6 run "${SCRIPT_DIR}/soak.js" \
      --out "json=${RESULTS_DIR}/soak-${TIMESTAMP}.json"
    ;;
  auth)
    echo "Verifying auth against $BASE_URL ..."
    k6 run "${SCRIPT_DIR}/auth_setup.js"
    ;;
  *)
    echo "Usage: $0 [health|search|soak|auth]"
    echo ""
    echo "  health  — baseline health check (p95 < 100ms)"
    echo "  search  — peak load test at 50 req/s (p95 < 250ms) — sprint exit criterion"
    echo "  soak    — 2-hour sustained load test"
    echo "  auth    — verify login works before running other tests"
    echo ""
    echo "Environment variables:"
    echo "  BASE_URL      (default: https://consumer.flavorfind.co.ke)"
    echo "  TEST_EMAIL    (default: loadtest@flavorfind.co.ke)"
    echo "  TEST_PASSWORD (default: LoadTest!2026)"
    exit 1
    ;;
esac
