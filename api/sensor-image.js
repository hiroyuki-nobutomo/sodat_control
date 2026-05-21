// Vercel Serverless Function: GET /api/sensor-image?id=<DRIVE_FILE_ID>
//
// Server-side proxy for camera thumbnails stored in Drive. Lets the
// dashboard `<img>` tags render without making the Drive files
// publicly shared and without depending on Drive's flaky
// uc?export=view redirect chain.
//
// Authorization model: the Service Account behind SODAT_SERVICE_ACCOUNT_JSON_B64
// can only see files it has been granted access to (Content Manager on the
// lab's Shared Drive). Any fileId outside that scope returns 404 from
// Drive — no allow-list needed at this layer.

import { fetchImageStream } from "../lib/sensor_data.js";

// Drive file ids are limited to URL-safe base64-ish characters. Reject
// anything else outright so we don't even contact Drive on bad input.
const FILE_ID_RE = /^[A-Za-z0-9_-]+$/;

export default async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Cache-Control", "no-store");
    return res.status(405).send("Method not allowed (use GET).");
  }
  const id = typeof req.query.id === "string" ? req.query.id : "";
  if (!id || !FILE_ID_RE.test(id) || id.length > 128) {
    res.setHeader("Cache-Control", "no-store");
    return res.status(400).send("invalid id");
  }
  try {
    const { stream, mimeType } = await fetchImageStream(id);
    res.setHeader("Content-Type", mimeType);
    // Images on Drive are content-addressed by id — once a file id
    // exists, the bytes do not change. Cache aggressively at the edge.
    res.setHeader(
      "Cache-Control",
      "public, s-maxage=86400, stale-while-revalidate=604800, immutable"
    );
    stream.pipe(res);
  } catch (e) {
    // Treat 4xx Drive errors as 404 to the client (the id was bad or
    // we no longer have permission). Other failures bubble as 502.
    const status = e?.code === 404 || e?.response?.status === 404 ? 404 : 502;
    res.setHeader("Cache-Control", "no-store");
    return res.status(status).send(status === 404 ? "not found" : "upstream error");
  }
}
