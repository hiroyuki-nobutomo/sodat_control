// Vercel Serverless Function: GET /api/dashboard-data
//
// Returns the JSON bundle that drives the sensor dashboard. All access
// to the master spreadsheet is behind lib/sensor_data.js; this file only
// does HTTP concerns: caching headers, content negotiation, error shape.

import { fetchDashboardData } from "../lib/sensor_data.js";

export default async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Cache-Control", "no-store");
    return res.status(405).json({ error: "Method not allowed (use GET)." });
  }
  try {
    const data = await fetchDashboardData();
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    // 10-min fresh + 10-min stale-while-revalidate: the dashboard auto-refreshes
    // every 10 min, so align the edge cache to that cadence. Keeps the Sheets API
    // call count per Vercel edge region to ~1/10min regardless of viewer count.
    res.setHeader("Cache-Control", "public, s-maxage=600, stale-while-revalidate=600");
    return res.status(200).json(data);
  } catch (e) {
    // Surface the message but redact things that shouldn't leak through
    // the response body: PEM blocks (google-auth-library sometimes echoes
    // PEM fragments in stack traces) and the SA's client_email (occasionally
    // present in "Invalid grant for X" messages).
    const safeMsg =
      typeof e?.message === "string"
        ? e.message
            .replace(/-----BEGIN[\s\S]+?-----END[^-]+-----/g, "[redacted-pem]")
            .replace(/[\w.+-]+@[\w-]+\.iam\.gserviceaccount\.com/g, "[redacted-sa-email]")
        : "Unknown error";
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    return res.status(500).json({ error: "dashboard-data fetch failed", detail: safeMsg });
  }
}
