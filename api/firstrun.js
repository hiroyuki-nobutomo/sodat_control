// Vercel Serverless Function: GET /api/firstrun?user=<unix-username>&token=<access-token>
//
// Returns the SD-card firstrun snippet pre-filled with the project's
// service-account key (read from the SODAT_SERVICE_ACCOUNT_JSON_B64 env var,
// set in the Vercel dashboard) and the requested Pi Imager username.
//
// Access is gated by a shared lab token (SODAT_ACCESS_TOKEN env var). Lab
// admins distribute the token to researchers as part of the URL:
//     https://<host>/?token=<the-secret>
// — that way researchers don't have to type the token, but knowing the URL
// (without the token) is not enough to extract the service-account key.
// Token rotation = change the env var and redeploy; old links die instantly.

import { timingSafeEqual } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const TEMPLATE_PATH = join(__dirname, "..", "firstrun_snippet.sh.template");

// Linux usernames: lowercase letter first, then [a-z0-9_-], up to 32 chars.
const USER_RE = /^[a-z][a-z0-9_-]{0,31}$/;

// Sensor types the project currently supports. Must stay in sync with
// src/sensors/*.py and with KNOWN_SENSORS in docs/index.html (the Step 3
// checkbox list).
// (Mock is intentionally excluded — it's for unit tests, not field deployment.)
const KNOWN_SENSORS = new Set([
  "BME280",
  "TDSN7200",
  "TDSN7300",
  "IWS660CS",
  "Camera",
  "SerialJSON",
]);

function checkToken(req) {
  const expected = process.env.SODAT_ACCESS_TOKEN;
  if (!expected) {
    return {
      ok: false, status: 500,
      msg: "SODAT_ACCESS_TOKEN env var is not set on this Vercel project. " +
           "Set it in Project Settings -> Environment Variables (any random " +
           "string), then redeploy. Researchers append ?token=<that-value> to " +
           "the page URL.",
    };
  }
  const provided = typeof req.query.token === "string" ? req.query.token : "";
  if (!provided) {
    return {
      ok: false, status: 401,
      msg: "Missing access token. Append ?token=<your-lab-token> to the URL " +
           "(get it from the lab admin).",
    };
  }
  // Constant-time comparison to avoid timing side channels on the token.
  const a = Buffer.from(expected, "utf-8");
  const b = Buffer.from(provided, "utf-8");
  if (a.length !== b.length || !timingSafeEqual(a, b)) {
    return { ok: false, status: 401, msg: "Invalid access token." };
  }
  return { ok: true };
}

function fail(res, status, message) {
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.status(status).send(`# sodat-firstrun error: ${message}\n`);
}

export default function handler(req, res) {
  if (req.method !== "GET") {
    return fail(res, 405, "Method not allowed (use GET).");
  }

  const auth = checkToken(req);
  if (!auth.ok) {
    return fail(res, auth.status, auth.msg);
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

  // Sensor selection. "all" (or missing) means leave config.yaml's sensors
  // list untouched on the Pi. Otherwise the value must be a CSV of known
  // sensor types — unknown names are rejected to surface typos early instead
  // of silently producing a Pi that runs zero sensors.
  const rawSensors = typeof req.query.sensors === "string" ? req.query.sensors : "all";
  let sensorsValue;
  if (rawSensors.trim().toLowerCase() === "all" || rawSensors.trim() === "") {
    sensorsValue = "all";
  } else {
    const requested = rawSensors.split(",").map((s) => s.trim()).filter(Boolean);
    const unknown = requested.filter((s) => !KNOWN_SENSORS.has(s));
    if (unknown.length) {
      return fail(res, 400,
        `Unknown sensor type(s): ${unknown.join(", ")}. ` +
        `Supported: ${[...KNOWN_SENSORS].join(", ")} (or "all").`
      );
    }
    if (requested.length === 0) {
      return fail(res, 400, 'sensors=" " — pick at least one, or use sensors=all.');
    }
    sensorsValue = [...new Set(requested)].join(",");
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
    .replace("__SA_JSON_B64__", saB64)
    .replace("__SODAT_SENSORS__", sensorsValue);

  res.setHeader("Content-Type", "text/x-shellscript; charset=utf-8");
  res.setHeader("Content-Disposition", 'attachment; filename="sodat-firstrun-snippet.sh"');
  res.setHeader("Cache-Control", "no-store, no-cache, must-revalidate");
  res.status(200).send(filled);
}
