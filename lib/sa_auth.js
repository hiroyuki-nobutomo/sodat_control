// Shared service-account credential handling for the Vercel functions.
//
// Both /api/firstrun and /api/dashboard-data (via lib/sensor_data.js) need
// the same SA JSON, validated the same way. Without this module they each
// re-derive `{client_email, private_key}` from SODAT_SERVICE_ACCOUNT_JSON_B64
// on every request, with subtly different error messages.

import { JWT } from "google-auth-library";

// File ids inside Google Drive / Sheets are URL-safe base64-ish.
// Exported for any handler that takes a fileId query param.
export const FILE_ID_RE = /^[A-Za-z0-9_-]+$/;

/**
 * Decode + validate the SA JSON from env. Throws a self-describing error
 * if the env var is missing, malformed, or doesn't look like an SA key.
 *
 * Returns the parsed JSON object — callers decide whether to construct
 * a JWT from it or just validate (firstrun does the latter).
 */
export function decodeServiceAccountCreds() {
  const saB64 = process.env.SODAT_SERVICE_ACCOUNT_JSON_B64;
  if (!saB64) {
    throw new Error(
      "SODAT_SERVICE_ACCOUNT_JSON_B64 env var is not set on this Vercel project."
    );
  }
  let creds;
  try {
    const json = Buffer.from(saB64, "base64").toString("utf-8");
    creds = JSON.parse(json);
  } catch (e) {
    throw new Error(
      `SODAT_SERVICE_ACCOUNT_JSON_B64 does not contain valid base64-encoded JSON: ${e.message}`
    );
  }
  if (creds.type !== "service_account") {
    throw new Error('SODAT_SERVICE_ACCOUNT_JSON_B64 JSON is missing "type": "service_account".');
  }
  if (!creds.client_email || !creds.private_key) {
    throw new Error("SODAT_SERVICE_ACCOUNT_JSON_B64 is missing client_email or private_key.");
  }
  return creds;
}

// Lazy module-scope cache. The Vercel runtime reuses the warm Lambda
// across invocations, and JWT instances cache their own OAuth access
// tokens for ~1 h — so building a fresh JWT per request both re-parses
// the PEM key and forfeits the token cache. One JWT per (set of scopes)
// per warm instance is enough.
const _jwtCache = new Map();

/**
 * Return a (cached) JWT auth client narrowed to the requested scopes.
 * Pass the same array reference across calls to hit the cache.
 */
export function getAuthClient(scopes) {
  const key = scopes.slice().sort().join("|");
  let jwt = _jwtCache.get(key);
  if (jwt) return jwt;
  const creds = decodeServiceAccountCreds();
  jwt = new JWT({
    email: creds.client_email,
    key: creds.private_key,
    scopes,
  });
  _jwtCache.set(key, jwt);
  return jwt;
}
