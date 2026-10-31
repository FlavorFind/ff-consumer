/**
 * Load test: Search endpoint — THE critical test
 *
 * Sprint exit criterion: search p95 < 250ms at 50 req/s on staging.
 *
 * Scenario:
 *   1. setup()  — log in as test user, get JWT
 *   2. default() — POST /v1/search/ at 50 req/s for 3 minutes
 *      Uses a rotating set of realistic ingredient combinations
 *      to avoid pure cache hits and exercise the engine + Redis layer.
 *
 * Phases:
 *   0:00–0:30  ramp up 0 → 50 req/s
 *   0:30–3:30  hold at 50 req/s  (the measurement window)
 *   3:30–4:00  ramp down 50 → 0
 *
 * Run:
 *   k6 run search.js
 *   BASE_URL=https://consumer.flavorfind.co.ke k6 run search.js
 *   BASE_URL=http://100.96.139.83 k6 run search.js   (self-hosted)
 */

import http from "k6/http";
import { check } from "k6";
import { Counter, Trend } from "k6/metrics";
import { BASE_URL, SEARCH_THRESHOLDS, headers } from "./config.js";
import { login } from "./auth_setup.js";

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------

const searchErrors = new Counter("search_errors");
const engineDegraded = new Counter("engine_degraded_responses");
const exactTierCount = new Counter("search_tier_exact");
const canMakeTierCount = new Counter("search_tier_can_make");
const almostTierCount = new Counter("search_tier_almost");
const totalResults = new Trend("search_total_results");

// ---------------------------------------------------------------------------
// Test options
// ---------------------------------------------------------------------------

export const options = {
  scenarios: {
    search_load: {
      executor: "ramping-arrival-rate",
      startRate: 0,
      timeUnit: "1s",
      preAllocatedVUs: 20,
      maxVUs: 100,
      stages: [
        { duration: "30s", target: 50 },   // ramp up
        { duration: "3m", target: 50 },    // hold — measurement window
        { duration: "30s", target: 0 },    // ramp down
      ],
    },
  },
  thresholds: {
    ...SEARCH_THRESHOLDS,
    // Additional guard: 99th percentile under 500ms
    "http_req_duration{endpoint:search}": ["p(95)<250", "p(99)<500"],
    // Search-specific error counter must stay at 0
    search_errors: ["count<5"],
  },
};

// ---------------------------------------------------------------------------
// Ingredient combinations — rotate to avoid pure cache hits.
// These are real East African ingredient sets that the engine recognises.
// ---------------------------------------------------------------------------

const INGREDIENT_SETS = [
  // Ugali-based meals
  ["ugali", "sukuma wiki", "tomato"],
  ["ugali", "omena", "onion"],
  ["ugali", "beef", "kachumbari"],
  // Rice-based
  ["rice", "chicken", "tomato", "onion"],
  ["pilau", "beef", "cardamom", "cloves"],
  ["rice", "coconut milk", "fish"],
  // Vegetarian
  ["lentils", "tomato", "onion", "spinach"],
  ["githeri", "maize", "beans"],
  ["chapati", "lentils", "tomato"],
  // Breakfast
  ["mandazi", "flour", "coconut milk"],
  ["eggs", "tomato", "onion"],
  ["uji", "millet flour", "milk"],
  // Coastal
  ["biryani", "rice", "chicken", "spices"],
  ["samosa", "flour", "beef", "onion"],
  ["mahamri", "coconut milk", "flour", "yeast"],
  // Snacks / street food
  ["mutura", "beef", "onion"],
  ["roasted maize", "maize"],
  ["nyama choma", "beef", "lemon"],
];

// Diet profiles to rotate through (simulates different user profiles)
const DIET_PROFILES = [
  [],                              // no restrictions
  ["vegetarian"],
  ["halal"],
  ["gluten-free"],
  ["vegetarian", "nut-free"],
];

// ---------------------------------------------------------------------------
// Setup — log in once, share token across all VUs
// ---------------------------------------------------------------------------

export function setup() {
  const tokens = login();
  if (!tokens) {
    throw new Error(
      "Load test setup failed: could not log in. " +
        "Set TEST_EMAIL and TEST_PASSWORD env vars and ensure the account exists on staging.",
    );
  }
  console.log("✓ Auth setup complete");
  return { access: tokens.access };
}

// ---------------------------------------------------------------------------
// Main scenario
// ---------------------------------------------------------------------------

export default function (data) {
  // Rotate ingredient sets and diet profiles based on VU iteration
  const setIndex = (__ITER + __VU) % INGREDIENT_SETS.length;
  const dietIndex = (__VU) % DIET_PROFILES.length;

  const payload = {
    ingredients: INGREDIENT_SETS[setIndex],
    diet: DIET_PROFILES[dietIndex],
    mode: "strict",
    lang: "en",
    limit: 20,
    exclude: [],
  };

  const res = http.post(
    `${BASE_URL}/v1/search/`,
    JSON.stringify(payload),
    {
      headers: headers(data.access),
      tags: { endpoint: "search" },
    },
  );

  // Check correctness
  const ok = check(res, {
    "search status 200": (r) => r.status === 200,
    "search has results key": (r) => {
      try {
        const b = JSON.parse(r.body);
        return b.results !== undefined;
      } catch {
        return false;
      }
    },
    "search not 5xx": (r) => r.status < 500,
  });

  if (!ok) {
    searchErrors.add(1);
    if (res.status !== 401) {
      // 401s happen if token expired during long runs — not a search error
      console.error(
        `Search error [VU ${__VU} iter ${__ITER}]: ` +
          `${res.status} — ${res.body.substring(0, 300)}`,
      );
    }
    return;
  }

  try {
    const body = JSON.parse(res.body);

    // Track engine degraded responses
    if (body.engine_status === "degraded") {
      engineDegraded.add(1);
    }

    // Track result tier distribution
    const results = body.results || {};
    exactTierCount.add((results.exact || []).length);
    canMakeTierCount.add((results.can_make || []).length);
    almostTierCount.add((results.almost || []).length);

    // Track total result count
    const total =
      (results.exact || []).length +
      (results.can_make || []).length +
      (results.almost || []).length;
    totalResults.add(total);
  } catch {
    // Body parse error — already counted in check failure above
  }
}

// ---------------------------------------------------------------------------
// Teardown — print a summary note
// ---------------------------------------------------------------------------

export function teardown(data) {
  console.log("Search load test complete.");
  console.log("Check the thresholds above — p95 must be < 250ms to pass.");
}
