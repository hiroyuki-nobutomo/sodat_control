// Vercel Serverless Function: GET /api/sensor-image?id=<DRIVE_FILE_ID>
//
// Server-side proxy for camera thumbnails stored in Drive. Lets dashboard
// <img> tags render without making the Drive files publicly shared and
// without depending on Drive's flaky uc?export=view redirect chain.
//
// Authorization model: the SA can only see files it has been granted
// access to (Content Manager on the lab's Shared Drive). Any fileId
// outside that scope returns 404 from Drive — no allow-list needed here.

import { fetchImageStream } from "../lib/sensor_data.js";
import { FILE_ID_RE } from "../lib/sa_auth.js";

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
    // Drive files are content-addressed by id — bytes don't change. Cache hard.
    res.setHeader(
      "Cache-Control",
      "public, s-maxage=86400, stale-while-revalidate=604800, immutable"
    );
    stream.pipe(res);
  } catch (e) {
    const status = e?.code === 404 || e?.response?.status === 404 ? 404 : 502;
    res.setHeader("Cache-Control", "no-store");
    return res.status(status).send(status === 404 ? "not found" : "upstream error");
  }
}
