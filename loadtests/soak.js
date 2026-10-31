/**
 * Soak test — 2-hour sustained load
 *
 * Sprint exit criterion: 2-hour sustained load at realistic concurrency
 * with no memory leaks, no error rate increase over time, and no
 * degradation of p95 latency.
 *
 * Lower rate than the peak load test (20 req/s instead of 50) but
 * sustained for 2 hours to expose memory leaks, connection pool exhaustion,
 * and slow cache poisoning.
 *
 * What it exercises:
 *   - Search (60% of traffic)
 *   - Dish detail proxy (20%)
 *   - Pantry list (10%)
 *   - Health check (10%)
 *
 * Run (takes 2 hours — run in a tmux session):
 *   BASE_URL=https://consumer.flavorfind.co.ke k6 run soak.js
 *   BASE_URL=https://consumer.flavorfind.co.ke k6 run soak.js --out json=results/soak-$(date +%Y%m%d).json
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";
import { BASE_URL, headers } from "./config.js";
import { login } from "./auth_setup.js";

// ---------------------------------------------------------------------------
// Token refresh helper
// Refreshes the access token using the refresh token.
// Called inline whenever a 401 is detected.
// ---------------------------------------------------------------------------
function refreshToken(refreshToken) {
  const res = http.post(
    `${BASE_URL}/v1/auth/refresh/`,
    JSON.stringify({ refresh: refreshToken }),
    { headers: headers(null) },
  );
  if (res.status === 200) {
    const body = JSON.parse(res.body);
    return body.access;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Metrics
// ---------------------------------------------------------------------------

const errorRate = new Rate("error_rate");
const searchLatency = new Trend("search_latency_soak", true);
const dishLatency = new Trend("dish_latency_soak", true);

// ---------------------------------------------------------------------------
// Options
// ---------------------------------------------------------------------------

export const options = {
  scenarios: {
    soak: {
      executor: "constant-arrival-rate",
      rate: 20,         // 20 req/s sustained
      timeUnit: "1s",
      duration: "2h",
      preAllocatedVUs: 15,
      maxVUs: 50,
    },
  },
  thresholds: {
    // Over 2 hours these must hold
    "http_req_duration{endpoint:search}": ["p(95)<400"],   // relaxed vs peak test
    "http_req_duration{endpoint:health}": ["p(95)<150"],
    error_rate: ["rate<0.02"],   // < 2% 5xx errors over 2 hours (excludes 401/429)
    // NOTE: http_req_failed is intentionally NOT gated here — it counts 401/429
    // which are expected (token expiry, rate limiting). Gate only on error_rate
    // which tracks 5xx specifically.
  },
};

// ---------------------------------------------------------------------------
// Dish slugs to rotate through (from East African cuisine)
// ---------------------------------------------------------------------------

const DISH_SLUGS = [
  "ugali-sukuma-wiki",
  "nyama-choma",
  "pilau",
  "chapati",
  "githeri",
  "mandazi",
  "biryani",
  "samosa",
  "mukimo",
  "matoke",
];

const INGREDIENT_SETS = [
  ["ugali", "sukuma wiki", "tomato"],
  ["rice", "chicken", "tomato", "onion"],
  ["lentils", "tomato", "onion"],
  ["chapati", "beef", "onion"],
  ["eggs", "tomato", "onion"],
  ["matoke", "beans", "groundnuts"],
  ["tilapia", "tomato", "lemon"],
  ["ugali", "omena", "onion"],
];

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

export function setup() {
  const tokens = login();
  if (!tokens) {
    throw new Error("Soak test setup failed: could not log in.");
  }
  console.log("✓ Soak test auth setup complete. Running for 2 hours...");
  return { access: tokens.access, refresh: tokens.refresh };
}

// ---------------------------------------------------------------------------
// Main scenario — weighted traffic mix
// ---------------------------------------------------------------------------

export default function (data) {
  const roll = Math.random();

  if (roll < 0.1) {
    // 10% — health check (unauthenticated, no token needed)
    const res = http.get(`${BASE_URL}/v1/health/`, {
      headers: headers(null),
      tags: { endpoint: "health" },
    });
    // Health returns 429 if polled too aggressively — count only 5xx as errors
    errorRate.add(res.status >= 500 ? 1 : 0);
    check(res, { "health ok (200 or 429)": (r) => r.status === 200 || r.status === 429 });
  } else if (roll < 0.3) {
    // 20% — dish detail
    const slug = DISH_SLUGS[__ITER % DISH_SLUGS.length];
    let res = http.get(`${BASE_URL}/v1/dishes/${slug}/`, {
      headers: headers(data.access),
      tags: { endpoint: "dish" },
    });
    // Token expired — refresh and retry once
    if (res.status === 401 && data.refresh) {
      const newAccess = refreshToken(data.refresh);
      if (newAccess) {
        data.access = newAccess;
        res = http.get(`${BASE_URL}/v1/dishes/${slug}/`, {
          headers: headers(data.access),
          tags: { endpoint: "dish" },
        });
      }
    }
    dishLatency.add(res.timings.duration);
    errorRate.add(res.status >= 500 ? 1 : 0);
    check(res, { "dish status 200 or 404": (r) => r.status === 200 || r.status === 404 });
  } else if (roll < 0.4) {
    // 10% — pantry list
    let res = http.get(`${BASE_URL}/v1/pantry/`, {
      headers: headers(data.access),
      tags: { endpoint: "pantry" },
    });
    if (res.status === 401 && data.refresh) {
      const newAccess = refreshToken(data.refresh);
      if (newAccess) {
        data.access = newAccess;
        res = http.get(`${BASE_URL}/v1/pantry/`, {
          headers: headers(data.access),
          tags: { endpoint: "pantry" },
        });
      }
    }
    errorRate.add(res.status >= 500 ? 1 : 0);
    check(res, { "pantry status 200": (r) => r.status === 200 });
  } else {
    // 60% — search (the critical path)
    const setIndex = __ITER % INGREDIENT_SETS.length;
    const payload = JSON.stringify({
      ingredients: INGREDIENT_SETS[setIndex],
      diet: [],
      mode: "strict",
      lang: "en",
      limit: 20,
      exclude: [],
    });
    let res = http.post(`${BASE_URL}/v1/search/`, payload, {
      headers: headers(data.access),
      tags: { endpoint: "search" },
    });
    // Token expired — refresh and retry once
    if (res.status === 401 && data.refresh) {
      const newAccess = refreshToken(data.refresh);
      if (newAccess) {
        data.access = newAccess;
        res = http.post(`${BASE_URL}/v1/search/`, payload, {
          headers: headers(data.access),
          tags: { endpoint: "search" },
        });
      }
    }
    searchLatency.add(res.timings.duration);
    errorRate.add(res.status >= 500 ? 1 : 0);
    check(res, {
      "search status 200": (r) => r.status === 200,
      "search not 5xx": (r) => r.status < 500,
    });
  }
}

export function teardown() {
  console.log("Soak test complete. Review error_rate and latency trends over time.");
  console.log("If p95 increased significantly after hour 1, investigate memory/connection leaks.");
}
