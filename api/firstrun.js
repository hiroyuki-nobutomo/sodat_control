// Vercel Serverless Function: GET /api/firstrun?user=<unix-username>
//
// Returns the SD-card firstrun snippet pre-filled with the project's
// service-account key (read from the SODAT_SERVICE_ACCOUNT_JSON_B64 env var,
// set in the Vercel dashboard) and the requested Pi Imager username.
//
// Researchers don't need to handle the service_account.json themselves — they
// just enter their username and click Download. The page that drives this
// endpoint MUST be behind Vercel Deployment Protection (Pro) or equivalent,
// since unauthenticated access to /api/firstrun would leak project Drive
// write credentials.

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const TEMPLATE_PATH = join(__dirname, "..", "firstrun_snippet.sh.template");

// Linux usernames: lowercase letter first, then [a-z0-9_-], up to 32 chars.
const USER_RE = /^[a-z][a-z0-9_-]{0,31}$/;

function fail(res, status, message) {
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.status(status).send(`# sodat-firstrun error: ${message}\n`);
}

export default function handler(req, res) {
  if (req.method !== "GET") {
    return fail(res, 405, "Method not allowed (use GET).");
  }

  const saB64 = process.env.SODAT_SERVICE_ACCOUNT_JSON_B64;
  if (!saB64) {
    return fail(res, 500,
      "SODAT_SERVICE_ACCOUNT_JSON_B64 env var is not set on this Vercel project. " +
      "Set it in the Vercel dashboard (Project Settings -> Environment Variables) " +
      "to the base64-encoded contents of service_account.json."
    );
  }

  // Validate the env var actually decodes to a service-account key —
  // catches paste errors early instead of producing a broken SD card.
  let decoded;
  try {
    decoded = Buffer.from(saB64, "base64").toString("utf-8");
    const obj = JSON.parse(decoded);
    if (obj.type !== "service_account") {
      throw new Error('JSON is missing "type": "service_account"');
    }
    if (!obj.client_email || !obj.private_key) {
      throw new Error("JSON is missing client_email or private_key");
    }
  } catch (e) {
    return fail(res, 500,
      `SODAT_SERVICE_ACCOUNT_JSON_B64 does not contain a valid service-account JSON: ${e.message}`
    );
  }

  const rawUser = typeof req.query.user === "string" ? req.query.user : "sodat";
  if (!USER_RE.test(rawUser)) {
    return fail(res, 400,
      `Invalid user "${rawUser}": must match ${USER_RE}.`
    );
  }

  let template;
  try {
    template = readFileSync(TEMPLATE_PATH, "utf-8");
  } catch (e) {
    return fail(res, 500,
      `Could not read firstrun_snippet.sh.template from the deployment bundle: ${e.message}. ` +
      "Check that vercel.json's functions.includeFiles is configured."
    );
  }

  const filled = template
    .replace("__SODAT_USER__", rawUser)
    .replace("__SA_JSON_B64__", saB64);

  res.setHeader("Content-Type", "text/x-shellscript; charset=utf-8");
  res.setHeader("Content-Disposition", 'attachment; filename="sodat-firstrun-snippet.sh"');
  res.setHeader("Cache-Control", "no-store, no-cache, must-revalidate");
  res.status(200).send(filled);
}
