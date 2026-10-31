/**
 * Load test: Health check endpoint
 *
 * Purpose: warm-up baseline — verify the server handles load before
 * running the heavier search tests. Also useful for checking that
 * the engine is reachable from the consumer backend.
 *
 * Target: GET /v1/health/ — p95 < 100ms at 50 req/s
 *
 * Run:
 *   k6 run health.js
 *   BASE_URL=https://consumer.flavorfind.co.ke k6 run health.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { BASE_URL, HEALTH_THRESHOLDS, headers } from "./config.js";

export const options = {
  // Ramp up to 50 req/s, hold for 1 minute, ramp down
  scenarios: {
    health_check: {
      executor: "constant-arrival-rate",
      rate: 50,           // 50 iterations per second
      timeUnit: "1s",
      duration: "1m",
      preAllocatedVUs: 10,
      maxVUs: 20,
    },
  },
  thresholds: HEALTH_THRESHOLDS,
};

export default function () {
  const res = http.get(`${BASE_URL}/v1/health/`, {
    headers: headers(null),
    tags: { endpoint: "health" },
  });

  check(res, {
    "health status 200": (r) => r.status === 200,
    "health status ok": (r) => {
      try {
        return JSON.parse(r.body).status === "ok";
      } catch {
        return false;
      }
    },
  });

  // No sleep needed with constant-arrival-rate executor
}
