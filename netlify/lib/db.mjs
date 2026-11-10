// Shared Neon connection + one-time schema bootstrap.
import { neon } from "@neondatabase/serverless";

let sql;
let ready;

export function getSql() {
  if (!sql) {
    const url = process.env.DATABASE_URL || process.env.NETLIFY_DATABASE_URL;
    if (!url) throw new Error("DATABASE_URL is not set");
    sql = neon(url);
  }
  return sql;
}

// Keep in sync with db/schema.sql.
const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS visitors (
     visitor_id uuid PRIMARY KEY,
     first_seen timestamptz NOT NULL DEFAULT now(),
     last_seen  timestamptz NOT NULL DEFAULT now())`,
  `CREATE INDEX IF NOT EXISTS visitors_last_seen_idx ON visitors (last_seen)`,
  `CREATE TABLE IF NOT EXISTS visitor_days (
     day        date NOT NULL,
     visitor_id uuid NOT NULL REFERENCES visitors (visitor_id) ON DELETE CASCADE,
     PRIMARY KEY (day, visitor_id))`,
  `CREATE TABLE IF NOT EXISTS download_events (
     id         bigserial PRIMARY KEY,
     visitor_id uuid NOT NULL,
     platform   text NOT NULL CHECK (platform IN ('windows', 'mac')),
     created_at timestamptz NOT NULL DEFAULT now())`,
  `CREATE INDEX IF NOT EXISTS download_events_created_idx ON download_events (created_at)`,
  `CREATE INDEX IF NOT EXISTS download_events_dedupe_idx ON download_events (visitor_id, platform, created_at)`,
  `CREATE TABLE IF NOT EXISTS admin_login_attempts (
     id      bigserial PRIMARY KEY,
     ip_hash text NOT NULL,
     at      timestamptz NOT NULL DEFAULT now())`,
  `CREATE INDEX IF NOT EXISTS admin_login_attempts_idx ON admin_login_attempts (ip_hash, at)`,
];

export function ensureSchema() {
  ready ??= (async () => {
    const s = getSql();
    const rows = await s.query("SELECT to_regclass('public.admin_login_attempts') AS t");
    if (rows[0]?.t) return; // already created
    await s.transaction(SCHEMA.map((stmt) => s.query(stmt)));
  })().catch((err) => {
    ready = undefined; // retry on the next request
    throw err;
  });
  return ready;
}

export function json(status, body, headers = {}) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers },
  });
}
