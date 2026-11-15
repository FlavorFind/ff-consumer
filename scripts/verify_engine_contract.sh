#!/usr/bin/env bash
# Verify ff-engine responses against the ff-consumer contract.
# Contract register: ff-engine/docs/debugging-plan-2026-11-12.md §3.
#
# Usage:
#   scripts/verify_engine_contract.sh <engine-base-url> <public-api-key> [internal-api-key]
#
# Optional:
#   DISH_SLUG=githeri      dish used for detail/missing checks
#   RUN_SUBMISSION=1       also POST a sample submission (writes to the engine)
#   INGREDIENT_ID=<uuid>   id sent to the missing endpoint
#
# Exits non-zero if any required contract field is missing.

set -euo pipefail

ENGINE="${1:-}"
KEY="${2:-}"
INTERNAL_KEY="${3:-}"
DISH_SLUG="${DISH_SLUG:-githeri}"
INGREDIENT_ID="${INGREDIENT_ID:-}"

if [[ -z "$ENGINE" || -z "$KEY" ]]; then
  echo "usage: $0 <engine-base-url> <public-api-key> [internal-api-key]" >&2
  exit 2
fi

command -v jq >/dev/null 2>&1 || {
  echo "jq is required but not installed" >&2
  exit 127
}

ENGINE="${ENGINE%/}"
API=(-H "X-API-Key: $KEY" -H "Content-Type: application/json")
failures=0

check() {
  local label="$1" json="$2" filter="$3"
  local value
  if value=$(jq -er "$filter" <<<"$json" 2>/dev/null); then
    echo "ok   $label -> $value"
  else
    echo "FAIL $label (missing or invalid: $filter)" >&2
    failures=$((failures + 1))
  fi
}

fetch() {
  local label="$1" method="$2" path="$3" body="${4:-}"
  local out
  if [[ "$method" == "GET" ]]; then
    out=$(curl -fsS "${API[@]}" "$ENGINE$path") || {
      echo "FAIL $label (HTTP request failed: GET $path)" >&2
      failures=$((failures + 1))
      return 0
    }
  else
    out=$(curl -fsS -X POST "${API[@]}" -d "$body" "$ENGINE$path") || {
      echo "FAIL $label (HTTP request failed: POST $path)" >&2
      failures=$((failures + 1))
      return 0
    }
  fi
  printf '%s' "$out"
}

echo "== version =="
VERSION_JSON=$(curl -fsS "$ENGINE/v1/meta/version/") || {
  echo "FAIL version (GET /v1/meta/version/)" >&2
  exit 1
}
check "engine_version" "$VERSION_JSON" '.engine_version'
check "dataset_version" "$VERSION_JSON" '.dataset_version'

echo "== search (no meal_type) =="
SEARCH_JSON=$(fetch "search" POST "/v1/search/by-ingredients" \
  '{"ingredients":["tomato","onion"],"mode":"strict","limit":5}') || true
if [[ -n "${SEARCH_JSON:-}" ]]; then
  check "results.exact is array" "$SEARCH_JSON" '.results.exact | type == "array"'
  check "first result dish_id" "$SEARCH_JSON" '.results.exact[0].dish_id'
  check "first result region_slugs" "$SEARCH_JSON" '.results.exact[0].region_slugs | type == "array"'
fi

echo "== dish detail =="
DISH_JSON=$(fetch "dish detail" GET "/v1/dishes/$DISH_SLUG/") || true
if [[ -n "${DISH_JSON:-}" ]]; then
  check "dish_id" "$DISH_JSON" '.dish_id'
  check "dietary_tags is array" "$DISH_JSON" '.dietary_tags | type == "array"'
fi

echo "== missing =="
MISSING_BODY='{"ingredient_ids":[]}'
if [[ -n "$INGREDIENT_ID" ]]; then
  MISSING_BODY=$(jq -cn --arg id "$INGREDIENT_ID" '{ingredient_ids: [$id]}')
fi
MISSING_JSON=$(fetch "missing" POST "/v1/dishes/$DISH_SLUG/missing/" "$MISSING_BODY") || true
if [[ -n "${MISSING_JSON:-}" ]]; then
  check "missing is array" "$MISSING_JSON" '.missing | type == "array"'
  check "cost_estimate_kes present" "$MISSING_JSON" 'has("cost_estimate_kes")'
  if [[ "$(jq -r '.missing | length' <<<"$MISSING_JSON")" -gt 0 ]]; then
    check "missing[0].ingredient_id" "$MISSING_JSON" '.missing[0].ingredient_id'
    check "missing[0].ingredient_slug" "$MISSING_JSON" '.missing[0].ingredient_slug'
    check "missing[0].ingredient_name" "$MISSING_JSON" '.missing[0].ingredient_name'
  fi
fi

echo "== dataset diff =="
DIFF_JSON=$(fetch "dataset diff" GET "/v1/datasets/diff/?since=0") || true
if [[ -n "${DIFF_JSON:-}" ]]; then
  check "current_version" "$DIFF_JSON" '.current_version'
fi

if [[ "$RUN_SUBMISSION" == "1" ]]; then
  if [[ -z "$INTERNAL_KEY" ]]; then
    echo "FAIL submission (RUN_SUBMISSION=1 requires an internal key)" >&2
    failures=$((failures + 1))
  else
    echo "== submission =="
    SUB_JSON=$(curl -fsS -X POST \
      -H "X-API-Key: $INTERNAL_KEY" -H "Content-Type: application/json" \
      -d '{"submission_type":"dish","payload":{"name_en":"Contract probe"},"submitter_note":"verify_engine_contract"}' \
      "$ENGINE/v1/internal/submissions/") || {
      echo "FAIL submission (POST /v1/internal/submissions/)" >&2
      failures=$((failures + 1))
      SUB_JSON=""
    }
    if [[ -n "${SUB_JSON:-}" ]]; then
      check "submission id" "$SUB_JSON" '.id'
    fi
  fi
fi

if [[ "$failures" -gt 0 ]]; then
  echo "contract verification FAILED ($failures check(s))" >&2
  exit 1
fi

echo "contract verification passed"
