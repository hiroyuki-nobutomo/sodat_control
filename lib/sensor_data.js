// Server-only data-source module for the Sodat sensor dashboard.
//
// All reads against the lab-wide master spreadsheet go through fetchDashboardData().
// The return shape is the stable contract between this module and the rest
// of the dashboard — keep it stable so swapping the backing store later
// (BigQuery, Postgres, …) only requires rewriting the body of this module
// while every consumer stays untouched.
//
// SECURITY: never call this module from anything that could end up in a
// browser bundle. SA scopes are narrowed to *.readonly here even though
// the key carries write scope.

import sheetsApi from "@googleapis/sheets";
import driveApi from "@googleapis/drive";
import { getAuthClient } from "./sa_auth.js";

/**
 * Data contract returned by fetchDashboardData(). Only the non-obvious
 * fields are documented; the property names speak for themselves.
 *
 * @typedef {Object} DashboardData
 * @property {ScalarRow[]} timeseries           one row per (sensor, metric, observation)
 * @property {DeviceInfo[]} devices             unique devices seen in `timeseries`
 * @property {string[]} sites                   unique sites derived from device-id prefix
 * @property {ImageRow[]} images
 * @property {string} updatedAt                 ISO ts of the fetch
 * @property {string} spreadsheetId             echoed for debugging
 *
 * @typedef {Object} ScalarRow
 * @property {number|string} value              numeric when sheet stored numeric, else passthrough
 *
 * @typedef {Object} ImageRow
 * @property {string} fileId                    extracted from the Drive URL so the page can route via /api/sensor-image?id=<fileId>
 *
 * @typedef {Object} DeviceInfo
 * @property {"SFC"|"AOI"|"OTHER"} site         derived from first letter of id (S→SFC, A→AOI, else OTHER)
 */

const SHEET_SCALAR_RANGE = "All!A:G";
const SHEET_IMAGES_RANGE = "Images!A:E";

const READ_ONLY_SCOPES = [
  "https://www.googleapis.com/auth/spreadsheets.readonly",
  "https://www.googleapis.com/auth/drive.readonly",
];

function getSpreadsheetId() {
  const id = process.env.SODAT_SPREADSHEET_ID;
  if (!id) {
    throw new Error("SODAT_SPREADSHEET_ID env var is not set on this Vercel project.");
  }
  return id;
}

function deviceSite(deviceId) {
  if (!deviceId) return "OTHER";
  const c = deviceId[0].toUpperCase();
  if (c === "S") return "SFC";
  if (c === "A") return "AOI";
  return "OTHER";
}

// Pull `fileId` out of any Drive URL shape we might see:
//   https://drive.google.com/uc?export=view&id=<ID>
//   https://drive.google.com/file/d/<ID>/view
//   https://drive.google.com/open?id=<ID>
function extractFileId(url) {
  if (!url || typeof url !== "string") return "";
  const m1 = url.match(/[?&]id=([A-Za-z0-9_-]+)/);
  if (m1) return m1[1];
  const m2 = url.match(/\/d\/([A-Za-z0-9_-]+)/);
  if (m2) return m2[1];
  return "";
}

// Coerce a cell's Value to Number when it parses cleanly; otherwise keep
// the raw string so non-numeric annotations the Pi might emit (e.g. "n/a")
// aren't silently destroyed. Empty / nullish → null so the downstream
// `typeof r.value !== "number"` check treats them uniformly as missing.
function coerceNumber(s) {
  if (s === null || s === undefined || s === "") return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : s;
}

// The Pi writes timestamps as "YYYY-MM-DD HH:MM:SS" JST strings, but if
// the master spreadsheet formats column A as Date, Sheets stores the cell
// as a serial number (days since 1899-12-30, fractional part = fraction
// of day) and UNFORMATTED_VALUE returns the serial. The dashboard's
// `parseJstTimestamp` only knows the string form, so we reconstruct it
// here. Serials are TZ-naive: we anchor the conversion in UTC and read
// UTC components so the wall-clock the Pi wrote into the cell survives
// unshifted (25569 = days from 1899-12-30 to 1970-01-01).
function coerceTimestamp(raw) {
  if (raw === null || raw === undefined || raw === "") return "";
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 1) return String(raw);
  const d = new Date(Math.round((n - 25569) * 86400000));
  const pad = (x) => String(x).padStart(2, "0");
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} `
       + `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

/**
 * Read both tabs of the master spreadsheet, normalise, return the bundle.
 * Both calls fire in parallel; either failing is fatal because the dashboard
 * surfaces (charts vs. camera strip) come from the two tabs.
 *
 * @returns {Promise<DashboardData>}
 */
export async function fetchDashboardData() {
  const auth = getAuthClient(READ_ONLY_SCOPES);
  const spreadsheetId = getSpreadsheetId();
  const sheets = sheetsApi.sheets({ version: "v4", auth });

  const [allRes, imagesRes] = await Promise.all([
    sheets.spreadsheets.values.get({
      spreadsheetId, range: SHEET_SCALAR_RANGE,
      valueRenderOption: "UNFORMATTED_VALUE",
    }),
    sheets.spreadsheets.values.get({
      spreadsheetId, range: SHEET_IMAGES_RANGE,
      valueRenderOption: "UNFORMATTED_VALUE",
    }),
  ]);

  const allRows = allRes.data.values || [];
  /** @type {ScalarRow[]} */
  const timeseries = [];
  for (let i = 1; i < allRows.length; i++) {
    const row = allRows[i];
    // Tolerate ragged rows (Sheets returns short arrays for trailing empties).
    if (!row || !row[0]) continue;
    timeseries.push({
      ts:         coerceTimestamp(row[0]),
      deviceId:   String(row[1] ?? ""),
      sensorType: String(row[2] ?? ""),
      sensorId:   String(row[3] ?? ""),
      metric:     String(row[4] ?? ""),
      value:      coerceNumber(row[5]),
      unit:       String(row[6] ?? ""),
    });
  }

  const deviceIds = [...new Set(timeseries.map((r) => r.deviceId).filter(Boolean))].sort();
  /** @type {DeviceInfo[]} */
  const devices = deviceIds.map((id) => ({ id, site: deviceSite(id) }));
  const sites = [...new Set(devices.map((d) => d.site))].sort();

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
      ts:       coerceTimestamp(row[0]),
      deviceId: String(row[1] ?? ""),
      sensorId: String(row[2] ?? ""),
      fileId,
      webViewLink,
    });
  }

  return {
    timeseries,
    devices,
    sites,
    images,
    updatedAt: new Date().toISOString(),
    spreadsheetId,
  };
}

/**
 * Drive read for a single file id. One round-trip: the streaming response's
 * own Content-Type header gives us the mime, so we don't probe metadata
 * first.
 *
 * @param {string} fileId
 * @returns {Promise<{stream: NodeJS.ReadableStream, mimeType: string}>}
 */
export async function fetchImageStream(fileId) {
  const auth = getAuthClient(READ_ONLY_SCOPES);
  const drive = driveApi.drive({ version: "v3", auth });
  const res = await drive.files.get(
    { fileId, alt: "media", supportsAllDrives: true },
    { responseType: "stream" }
  );
  const mimeType = res.headers?.["content-type"] || "image/jpeg";
  return { stream: res.data, mimeType };
}
