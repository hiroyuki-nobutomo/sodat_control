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
    // 15-min fresh + 15-min stale-while-revalidate: Pi uploads every 30 min,
    // so this keeps the Sheets API call count per Vercel edge region to ~1/15min
    // regardless of how many viewers are looking at the dashboard.
    res.setHeader("Cache-Control", "public, s-maxage=900, stale-while-revalidate=900");
    return res.status(200).json(data);
  } catch (e) {
    // Surface the message but redact any PEM block — google-auth-library
    // sometimes echoes PEM fragments in stack traces.
    const safeMsg =
      typeof e?.message === "string"
        ? e.message.replace(/-----BEGIN[\s\S]+?-----END[^-]+-----/g, "[redacted]")
        : "Unknown error";
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    return res.status(500).json({ error: "dashboard-data fetch failed", detail: safeMsg });
  }
}
