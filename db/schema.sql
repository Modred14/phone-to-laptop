-- Analytics schema for Neon Postgres.
-- The functions create this automatically on first use; this file is the
-- same thing for running by hand (psql / Neon SQL editor).
-- Privacy: no IP addresses, user agents, file names or file contents are stored.
-- visitor_id is a random UUID the browser generates for itself.

CREATE TABLE IF NOT EXISTS visitors (
  visitor_id uuid PRIMARY KEY,
  first_seen timestamptz NOT NULL DEFAULT now(),
  last_seen  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS visitors_last_seen_idx ON visitors (last_seen);

-- One row per visitor per UTC day: powers daily/weekly/monthly unique counts.
CREATE TABLE IF NOT EXISTS visitor_days (
  day        date NOT NULL,
  visitor_id uuid NOT NULL REFERENCES visitors (visitor_id) ON DELETE CASCADE,
  PRIMARY KEY (day, visitor_id)
);

-- A click on a Download button. Not a confirmed download or transfer.
CREATE TABLE IF NOT EXISTS download_events (
  id         bigserial PRIMARY KEY,
  visitor_id uuid NOT NULL,
  platform   text NOT NULL CHECK (platform IN ('windows', 'mac')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS download_events_created_idx ON download_events (created_at);
CREATE INDEX IF NOT EXISTS download_events_dedupe_idx ON download_events (visitor_id, platform, created_at);

-- Failed /admin login attempts (hashed IP only), for rate limiting.
CREATE TABLE IF NOT EXISTS admin_login_attempts (
  id      bigserial PRIMARY KEY,
  ip_hash text NOT NULL,
  at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS admin_login_attempts_idx ON admin_login_attempts (ip_hash, at);
