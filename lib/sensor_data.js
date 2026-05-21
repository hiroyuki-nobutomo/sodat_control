// Server-only data-source module for the Sodat sensor dashboard.
//
// All reads against the lab-wide master spreadsheet go through fetchDashboardData().
// The return shape is the stable contract between this module and the rest of
// the dashboard (API endpoint, client-side renderer) — keep it stable so
// swapping the backing store later (BigQuery, Postgres, …) only requires
// rewriting the body of this module while every consumer stays untouched.
//
// SECURITY:
// - Imports google-auth-library and reads SODAT_SERVICE_ACCOUNT_JSON_B64
//   directly from process.env. Never call this module from anything that
//   could end up in the browser bundle (i.e. /docs/* static files).
// - The SA key carries both read and write Drive scope; we restrict the
//   request-time scopes here to read-only and Sheets/Drive only.

import sheetsApi from "@googleapis/sheets";
import driveApi from "@googleapis/drive";
import { JWT } from "google-auth-library";

/**
 * @typedef {Object} ScalarRow
 * @property {string} ts          "YYYY-MM-DD HH:MM:SS" JST (as written by the Pi)
 * @property {string} deviceId
 * @property {string} sensorType
 * @property {string} sensorId
 * @property {string} metric
 * @property {number|string} value  numeric when sheet stored numeric, else string
 * @property {string} unit
 */

/**
 * @typedef {Object} ImageRow
 * @property {string} ts
 * @property {string} deviceId
 * @property {string} sensorId
 * @property {string} fileId          extracted from directLink so the dashboard can route via /api/sensor-image?id=<fileId>
 * @property {string} webViewLink     Drive UI link (opens in new tab)
 */

/**
 * @typedef {Object} DeviceInfo
 * @property {string} id              e.g. "S01"
 * @property {"SFC"|"AOI"|"OTHER"} site  derived from first letter of id
 */

/**
 * @typedef {Object<string, ScalarRow>} LatestByKey
 *   Key format: `${deviceId}|${metric}` — the most-recent ScalarRow we have
 *   for that combination. Used to populate KPI tiles without scanning the
 *   whole timeseries on the client.
 */

/**
 * @typedef {Object} DashboardData
 * @property {ScalarRow[]} timeseries
 * @property {LatestByKey} latest
 * @property {DeviceInfo[]} devices
 * @property {string[]} sites
 * @property {ImageRow[]} images
 * @property {string} updatedAt      ISO timestamp of the fetch (server clock)
 * @property {string} spreadsheetId  echoed for ops debugging; safe because it's not a secret
 */

const SHEET_SCALAR_RANGE = "All!A:G";
const SHEET_IMAGES_RANGE = "Images!A:E";

// Read-only scopes — the dashboard only reads. The Pi-side firstrun snippet
// still hands out a full-scope key, but each consumer narrows it here.
const READ_ONLY_SCOPES = [
  "https://www.googleapis.com/auth/spreadsheets.readonly",
  "https://www.googleapis.com/auth/drive.readonly",
];

/**
 * Build a JWT auth client from the base64-encoded SA JSON in process.env.
 * Throws (with a helpful message) when env is missing — those errors
 * bubble up to the API endpoint, which returns 500 with a redacted body.
 */
function makeAuth() {
  const saB64 = process.env.SODAT_SERVICE_ACCOUNT_JSON_B64;
  if (!saB64) {
    throw new Error(
      "SODAT_SERVICE_ACCOUNT_JSON_B64 env var is not set on this Vercel project."
    );
  }
  let credentials;
  try {
    const json = Buffer.from(saB64, "base64").toString("utf-8");
    credentials = JSON.parse(json);
  } catch (e) {
    throw new Error(
      `SODAT_SERVICE_ACCOUNT_JSON_B64 is not valid base64-encoded JSON: ${e.message}`
    );
  }
  if (!credentials.client_email || !credentials.private_key) {
    throw new Error(
      "SODAT_SERVICE_ACCOUNT_JSON_B64 is missing client_email / private_key."
    );
  }
  return new JWT({
    email: credentials.client_email,
    key: credentials.private_key,
    scopes: READ_ONLY_SCOPES,
  });
}

function getSpreadsheetId() {
  const id = process.env.SODAT_SPREADSHEET_ID;
  if (!id) {
    throw new Error(
      "SODAT_SPREADSHEET_ID env var is not set on this Vercel project."
    );
  }
  return id;
}

/**
 * Derive site bucket from the device-id prefix the lab uses:
 *   S* → SFC campus
 *   A* → API building (AOI)
 *   anything else → OTHER (so an unexpected id is visible, not hidden)
 */
function deviceSite(deviceId) {
  if (!deviceId) return "OTHER";
  const c = deviceId[0].toUpperCase();
  if (c === "S") return "SFC";
  if (c === "A") return "AOI";
  return "OTHER";
}

/**
 * Pull `fileId` out of any Drive URL shape we might see:
 *   https://drive.google.com/uc?export=view&id=<ID>
 *   https://drive.google.com/file/d/<ID>/view
 *   https://drive.google.com/open?id=<ID>
 * Returns "" when no id is present so the consumer can decide to skip.
 */
function extractFileId(url) {
  if (!url || typeof url !== "string") return "";
  const m1 = url.match(/[?&]id=([A-Za-z0-9_-]+)/);
  if (m1) return m1[1];
  const m2 = url.match(/\/d\/([A-Za-z0-9_-]+)/);
  if (m2) return m2[1];
  return "";
}

// Sheet rows arrive as string arrays. Coerce the Value column to Number when
// it parses cleanly; otherwise keep the raw string so we don't silently
// destroy non-numeric annotations the Pi might emit (e.g. "n/a").
function coerceNumber(s) {
  if (s === null || s === undefined || s === "") return s;
  const n = Number(s);
  return Number.isFinite(n) ? n : s;
}

/**
 * Single entry point. Reads both tabs of the master spreadsheet,
 * normalises them into the documented shape, and returns the bundle
 * the API endpoint serialises to JSON.
 *
 * Network calls happen in parallel. Either call failing is fatal because
 * the dashboard's two surfaces (charts vs. camera strip) come from the two
 * tabs; partial data would silently hide outages.
 *
 * @returns {Promise<DashboardData>}
 */
export async function fetchDashboardData() {
  const auth = makeAuth();
  const spreadsheetId = getSpreadsheetId();
  const sheets = sheetsApi.sheets({ version: "v4", auth });

  const [allRes, imagesRes] = await Promise.all([
    sheets.spreadsheets.values.get({
      spreadsheetId,
      range: SHEET_SCALAR_RANGE,
      valueRenderOption: "UNFORMATTED_VALUE",
    }),
    sheets.spreadsheets.values.get({
      spreadsheetId,
      range: SHEET_IMAGES_RANGE,
      valueRenderOption: "UNFORMATTED_VALUE",
    }),
  ]);

  // ---- All: drop the header row, project to ScalarRow ----------------------
  const allRows = allRes.data.values || [];
  /** @type {ScalarRow[]} */
  const timeseries = [];
  for (let i = 1; i < allRows.length; i++) {
    const row = allRows[i];
    // Tolerate ragged rows (sheets often return short arrays for trailing empties)
    if (!row || !row[0]) continue;
    timeseries.push({
      ts:         String(row[0] ?? ""),
      deviceId:   String(row[1] ?? ""),
      sensorType: String(row[2] ?? ""),
      sensorId:   String(row[3] ?? ""),
      metric:     String(row[4] ?? ""),
      value:      coerceNumber(row[5]),
      unit:       String(row[6] ?? ""),
    });
  }

  // ---- Latest per (deviceId, metric) — drives the KPI tiles ----------------
  /** @type {LatestByKey} */
  const latest = {};
  for (const r of timeseries) {
    if (!r.deviceId || !r.metric) continue;
    const key = `${r.deviceId}|${r.metric}`;
    const prior = latest[key];
    if (!prior || r.ts > prior.ts) {
      latest[key] = r;
    }
  }

  // ---- Devices + sites lists for the filter UI -----------------------------
  const deviceIds = [...new Set(timeseries.map((r) => r.deviceId).filter(Boolean))].sort();
  /** @type {DeviceInfo[]} */
  const devices = deviceIds.map((id) => ({ id, site: deviceSite(id) }));
  const sites = [...new Set(devices.map((d) => d.site))].sort();

  // ---- Images: project + extract fileId from the directLink ----------------
  const imageRows = imagesRes.data.values || [];
  /** @type {ImageRow[]} */
  const images = [];
  for (let i = 1; i < imageRows.length; i++) {
    const row = imageRows[i];
    if (!row || !row[0]) continue;
    const webViewLink = String(row[3] ?? "");
    const directLink  = String(row[4] ?? "");
    const fileId = extractFileId(directLink) || extractFileId(webViewLink);
    if (!fileId) continue;
    images.push({
      ts:       String(row[0] ?? ""),
      deviceId: String(row[1] ?? ""),
      sensorId: String(row[2] ?? ""),
      fileId,
      webViewLink,
    });
  }

  return {
    timeseries,
    latest,
    devices,
    sites,
    images,
    updatedAt: new Date().toISOString(),
    spreadsheetId,
  };
}

/**
 * Drive read for a single file id, returning a readable stream.
 * Used by the /api/sensor-image proxy so camera thumbnails render
 * without exposing Drive's public-share URLs.
 *
 * @param {string} fileId
 * @returns {Promise<{stream: NodeJS.ReadableStream, mimeType: string}>}
 */
export async function fetchImageStream(fileId) {
  const auth = makeAuth();
  const drive = driveApi.drive({ version: "v3", auth });
  // Probe metadata so we know the mime type to set on the response.
  const meta = await drive.files.get({
    fileId,
    fields: "mimeType",
    supportsAllDrives: true,
  });
  const mimeType = meta.data.mimeType || "application/octet-stream";
  const res = await drive.files.get(
    { fileId, alt: "media", supportsAllDrives: true },
    { responseType: "stream" }
  );
  return { stream: res.data, mimeType };
}
