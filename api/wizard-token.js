// Vercel Serverless Function: GET /api/wizard-token
//
// Returns SODAT_ACCESS_TOKEN so the dashboard's Pi-setup link can preload
// it without the researcher having to paste it manually first.
//
// THREAT MODEL: this endpoint is *not* token-gated; anyone who can reach
// the dashboard URL gets the wizard token by extension. The slug in
// /dashboard/sodat-<random> is the only access boundary, and it's the
// same boundary the dashboard URL itself uses. Operators rotate the
// SODAT_ACCESS_TOKEN env var in Vercel when they want to revoke; the
// next dashboard load picks it up (no edge caching here).

export default function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Cache-Control", "no-store");
    return res.status(405).send("Method not allowed (use GET).");
  }
  const token = process.env.SODAT_ACCESS_TOKEN;
  if (!token) {
    res.setHeader("Cache-Control", "no-store");
    return res.status(500).send(
      "SODAT_ACCESS_TOKEN env var is not set on this Vercel project."
    );
  }
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  // Never cache: a rotation should take effect on the very next request.
  res.setHeader("Cache-Control", "no-store");
  return res.status(200).send(token);
}
