/**
 * Auth setup helper — logs in a test user and returns a JWT access token.
 *
 * Used by other load test scripts via k6's setup() lifecycle function.
 * Run standalone to verify auth works before the main load tests:
 *
 *   k6 run auth_setup.js
 */

import http from "k6/http";
import { check } from "k6";
import { BASE_URL, TEST_USER, headers, AUTH_THRESHOLDS } from "./config.js";

export const options = {
  vus: 1,
  iterations: 1,
  thresholds: AUTH_THRESHOLDS,
};

/**
 * Logs in the test user and returns { access, refresh } tokens.
 * Call this from setup() in other scripts.
 */
export function login() {
  const res = http.post(
    `${BASE_URL}/v1/auth/login/`,
    JSON.stringify({
      email: TEST_USER.email,
      password: TEST_USER.password,
    }),
    { headers: headers(null), tags: { endpoint: "login" } },
  );

  const ok = check(res, {
    "login status 200": (r) => r.status === 200,
    "login has access token": (r) => {
      try {
        return JSON.parse(r.body).access !== undefined;
      } catch {
        return false;
      }
    },
  });

  if (!ok) {
    console.error(`Login failed: ${res.status} — ${res.body.substring(0, 500)}`);
    return null;
  }

  const body = JSON.parse(res.body);
  return { access: body.access, refresh: body.refresh };
}

// Standalone run — just verifies login works
export default function () {
  const tokens = login();
  if (tokens) {
    console.log(`✓ Login OK — token prefix: ${tokens.access.substring(0, 20)}...`);
  } else {
    console.error("✗ Login FAILED — check TEST_EMAIL/TEST_PASSWORD env vars");
  }
}
