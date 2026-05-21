// Vercel Serverless Function: GET /api/dashboard-data
//
// Returns the JSON bundle that drives the sensor dashboard. All access to
// the master spreadsheet (and any future swap to BigQuery / Postgres) is
// behind lib/sensor_data.js — this file only does HTTP concerns: caching,
// content negotiation, error shaping.
//
// Caching: 30-min upload cadence means the freshest data shifts every
// 30 minutes, so we cache at the edge for 15 minutes and serve stale for
// another 15 while we revalidate in the background. That's a single
// fetch of the Sheets API per ~15 minutes per Vercel edge region — well
// inside the Sheets quota even with many concurrent viewers.

import { fetchDashboardData } from "../lib/sensor_data.js";

export default async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Cache-Control", "no-store");
    return res.status(405).json({ error: "Method not allowed (use GET)." });
  }
  try {
    const data = await fetchDashboardData();
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    // 15-min fresh + 15-min stale-while-revalidate. The vercel.json
    // header rule used to slam Cache-Control: no-store on /api/*, but
    // that override is now scoped to /api/firstrun only.
    res.setHeader(
      "Cache-Control",
      "public, s-maxage=900, stale-while-revalidate=900"
    );
    return res.status(200).json(data);
  } catch (e) {
    // Surface the error message but never the SA key or stack from
    // google-auth-library (which can echo PEM fragments).
    const safeMsg =
      typeof e?.message === "string"
        ? e.message.replace(/-----BEGIN[\s\S]+?-----END[^-]+-----/g, "[redacted]")
        : "Unknown error";
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    return res.status(500).json({
      error: "dashboard-data fetch failed",
      detail: safeMsg,
    });
  }
}
