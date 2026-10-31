/**
 * Shared configuration for all ff-consumer load tests.
 *
 * Override BASE_URL and credentials via environment variables:
 *   BASE_URL=https://consumer.flavorfind.co.ke k6 run search.js
 */

export const BASE_URL = __ENV.BASE_URL || "https://consumer.flavorfind.co.ke";

// A pre-registered test user on staging.
// Create this account before running load tests:
//   POST /v1/auth/register/ with these credentials, then verify email.
export const TEST_USER = {
  email: __ENV.TEST_EMAIL || "loadtest@flavorfind.co.ke",
  password: __ENV.TEST_PASSWORD || "LoadTest!2026",
};

// Thresholds that must pass for the test to be considered green.
// Search p95 < 250ms is the hard requirement from the sprint exit criteria.
export const SEARCH_THRESHOLDS = {
  // p95 of all search requests must be under 250ms
  "http_req_duration{endpoint:search}": ["p(95)<250"],
  // Overall error rate must stay under 1%
  http_req_failed: ["rate<0.01"],
};

export const HEALTH_THRESHOLDS = {
  "http_req_duration{endpoint:health}": ["p(95)<100"],
  http_req_failed: ["rate<0.01"],
};

export const AUTH_THRESHOLDS = {
  "http_req_duration{endpoint:login}": ["p(95)<500"],
  http_req_failed: ["rate<0.01"],
};

// Standard headers for all requests
export function headers(token) {
  const h = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  if (token) {
    h["Authorization"] = `Bearer ${token}`;
  }
  return h;
}

// Log a summary line with key metrics
export function logThresholdResult(tag, res) {
  const ok = res.status >= 200 && res.status < 300;
  if (!ok) {
    console.error(`[${tag}] ${res.status} — ${res.body.substring(0, 200)}`);
  }
}
