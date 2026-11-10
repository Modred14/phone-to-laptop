// POST /api/track  { id, type: "view" | "ping" | "download", platform? }
// Records anonymous landing-page analytics. Stores only a random browser-made UUID,
// a UTC day, and (for downloads) "windows" or "mac". No IP, user agent or file data.
import { ensureSchema, getSql, json } from "../lib/db.mjs";

export const config = { path: "/api/track" };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const BOTS = /bot|crawl|spider|slurp|headless|preview|monitor|lighthouse|curl|wget/i;

const UPSERT_VISITOR = `
  WITH v AS (
    INSERT INTO visitors (visitor_id) VALUES ($1::uuid)
    ON CONFLICT (visitor_id) DO UPDATE SET last_seen = now()
    RETURNING visitor_id
  )
  INSERT INTO visitor_days (day, visitor_id)
  SELECT (now() AT TIME ZONE 'UTC')::date, visitor_id FROM v
  ON CONFLICT DO NOTHING`;

// Visitor upsert + download click in one statement. A repeat click by the same
// visitor on the same platform within 30 s (double click) is ignored.
const RECORD_DOWNLOAD = `
  WITH v AS (
    INSERT INTO visitors (visitor_id) VALUES ($1::uuid)
    ON CONFLICT (visitor_id) DO UPDATE SET last_seen = now()
    RETURNING visitor_id
  ), d AS (
    INSERT INTO visitor_days (day, visitor_id)
    SELECT (now() AT TIME ZONE 'UTC')::date, visitor_id FROM v
    ON CONFLICT DO NOTHING
  )
  INSERT INTO download_events (visitor_id, platform)
  SELECT $1::uuid, $2
  WHERE NOT EXISTS (
    SELECT 1 FROM download_events
    WHERE visitor_id = $1::uuid AND platform = $2 AND created_at > now() - interval '30 seconds'
  )`;

export default async (req) => {
  if (req.method !== "POST") return json(405, { error: "POST only" }, { allow: "POST" });

  // Same-origin only: the beacon is sent from our own page.
  const origin = req.headers.get("origin");
  if (origin) {
    let ok = false;
    try { ok = new URL(origin).host === new URL(req.url).host; } catch { /* bad origin */ }
    if (!ok) return json(403, { error: "forbidden" });
  }

  if (BOTS.test(req.headers.get("user-agent") || "")) return json(204);

  let body;
  try {
    const text = await req.text();
    if (text.length > 1024) return json(413, { error: "too large" });
    body = JSON.parse(text);
  } catch {
    return json(400, { error: "bad json" });
  }

  const id = typeof body?.id === "string" ? body.id.toLowerCase() : "";
  if (!UUID.test(id)) return json(400, { error: "bad id" });

  try {
    await ensureSchema();
    const sql = getSql();
    if (body.type === "view" || body.type === "ping") {
      await sql.query(UPSERT_VISITOR, [id]);
    } else if (body.type === "download" && (body.platform === "windows" || body.platform === "mac")) {
      await sql.query(RECORD_DOWNLOAD, [id, body.platform]);
    } else {
      return json(400, { error: "bad type" });
    }
    return json(204);
  } catch (err) {
    console.error("track failed:", err?.message);
    return json(500, { error: "server error" });
  }
};
