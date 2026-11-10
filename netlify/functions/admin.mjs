// /api/admin/login (POST), /api/admin/logout (POST), /api/admin/stats (GET)
import { ensureSchema, getSql, json } from "../lib/db.mjs";
import {
  COOKIE, SESSION_SECONDS, adminConfig, hashIp, passwordMatches,
  readCookie, sessionCookie, signSession, verifySession,
} from "../lib/auth.mjs";

export const config = { path: "/api/admin/*" };

const MAX_FAILS = 5; // per IP per 15 minutes
const TODAY = "(now() AT TIME ZONE 'UTC')::date";

// unit is one of our own constants, never user input.
function seriesSql(unit, count) {
  return `
  WITH b AS (
    SELECT generate_series(
      date_trunc('${unit}', ${TODAY}::timestamp) - interval '${count - 1} ${unit}',
      date_trunc('${unit}', ${TODAY}::timestamp),
      interval '1 ${unit}')::date AS bucket
  ), v AS (
    SELECT date_trunc('${unit}', day)::date AS bucket, count(DISTINCT visitor_id)::int AS n
    FROM visitor_days WHERE day >= (SELECT min(bucket) FROM b) GROUP BY 1
  ), d AS (
    SELECT date_trunc('${unit}', created_at AT TIME ZONE 'UTC')::date AS bucket, count(*)::int AS n
    FROM download_events
    WHERE created_at >= (SELECT min(bucket) FROM b)::timestamp AT TIME ZONE 'UTC' GROUP BY 1
  )
  SELECT to_char(b.bucket, 'YYYY-MM-DD') AS bucket,
         COALESCE(v.n, 0) AS visitors, COALESCE(d.n, 0) AS downloads
  FROM b LEFT JOIN v USING (bucket) LEFT JOIN d USING (bucket)
  ORDER BY b.bucket`;
}

const TOTALS_SQL = `
  SELECT
    (SELECT count(*) FROM visitors)::int AS unique_visitors,
    (SELECT count(*) FROM download_events)::int AS downloads,
    (SELECT count(*) FROM download_events WHERE platform = 'windows')::int AS downloads_windows,
    (SELECT count(*) FROM download_events WHERE platform = 'mac')::int AS downloads_mac,
    (SELECT count(*) FROM visitors WHERE last_seen > now() - interval '3 minutes')::int AS active_now`;

function windowSql(days) {
  return `
  SELECT
    (SELECT count(DISTINCT visitor_id) FROM visitor_days WHERE day > ${TODAY} - ${days})::int AS visitors,
    (SELECT count(*) FROM download_events
       WHERE (created_at AT TIME ZONE 'UTC')::date > ${TODAY} - ${days})::int AS downloads`;
}

async function stats() {
  const sql = getSql();
  const [totals, today, week, month, day, weekly, monthly] = await Promise.all([
    sql.query(TOTALS_SQL),
    sql.query(windowSql(1)),
    sql.query(windowSql(7)),
    sql.query(windowSql(30)),
    sql.query(seriesSql("day", 30)),
    sql.query(seriesSql("week", 12)),
    sql.query(seriesSql("month", 12)),
  ]);
  return {
    generatedAt: new Date().toISOString(),
    timezone: "UTC",
    totals: totals[0],
    windows: { today: today[0], last7: week[0], last30: month[0] },
    series: { day, week: weekly, month: monthly },
  };
}

async function login(req, context, cfg) {
  if (!(req.headers.get("content-type") || "").includes("application/json")) {
    return json(415, { error: "Unsupported content type" });
  }
  let body;
  try {
    const text = await req.text();
    if (text.length > 2048) return json(413, { error: "Too large" });
    body = JSON.parse(text);
  } catch {
    return json(400, { error: "Bad request" });
  }

  await ensureSchema();
  const sql = getSql();
  const ip = hashIp(cfg.secret, context?.ip || req.headers.get("x-nf-client-connection-ip"));

  const [{ n }] = await sql.query(
    "SELECT count(*)::int AS n FROM admin_login_attempts WHERE ip_hash = $1 AND at > now() - interval '15 minutes'",
    [ip],
  );
  if (n >= MAX_FAILS) {
    return json(429, { error: "Too many attempts. Try again in 15 minutes." }, { "retry-after": "900" });
  }

  if (typeof body?.password !== "string" || !passwordMatches(body.password, cfg.password)) {
    await sql.query("INSERT INTO admin_login_attempts (ip_hash) VALUES ($1)", [ip]);
    await sql.query("DELETE FROM admin_login_attempts WHERE at < now() - interval '1 day'");
    await new Promise((r) => setTimeout(r, 400)); // blunt fast guessing
    return json(401, { error: "Wrong password" });
  }

  await sql.query("DELETE FROM admin_login_attempts WHERE ip_hash = $1", [ip]);
  return json(200, { ok: true }, { "set-cookie": sessionCookie(req, signSession(cfg.secret), SESSION_SECONDS) });
}

export default async (req, context) => {
  const route = new URL(req.url).pathname.replace(/^\/api\/admin\/?/, "").replace(/\/$/, "");

  const cfg = adminConfig();
  if (cfg.error) {
    console.error("admin disabled:", cfg.error);
    return json(503, { error: "Admin is not configured on the server." });
  }

  try {
    if (route === "login" && req.method === "POST") return await login(req, context, cfg);

    if (route === "logout" && req.method === "POST") {
      return json(200, { ok: true }, { "set-cookie": sessionCookie(req, "", 0) });
    }

    if (route === "stats" && req.method === "GET") {
      if (!verifySession(cfg.secret, readCookie(req, COOKIE))) return json(401, { error: "Not signed in" });
      await ensureSchema();
      return json(200, await stats());
    }

    return json(404, { error: "Not found" });
  } catch (err) {
    console.error("admin failed:", err?.message);
    return json(500, { error: "Server error" });
  }
};
