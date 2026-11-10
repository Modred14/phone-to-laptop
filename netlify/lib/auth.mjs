// Single-owner admin auth: shared password -> signed, HttpOnly session cookie.
import { createHash, createHmac, timingSafeEqual } from "node:crypto";

export const COOKIE = "od_admin";
export const SESSION_SECONDS = 8 * 60 * 60;

export function adminConfig() {
  const password = process.env.ADMIN_PASSWORD || "";
  const secret = process.env.ADMIN_SESSION_SECRET || "";
  if (password.length < 12) return { error: "ADMIN_PASSWORD must be set and at least 12 characters." };
  if (secret.length < 32) return { error: "ADMIN_SESSION_SECRET must be set and at least 32 characters." };
  return { password, secret };
}

const sha = (s) => createHash("sha256").update(s).digest();

// Constant-time comparison that does not leak length.
export function passwordMatches(given, expected) {
  return timingSafeEqual(sha(String(given)), sha(String(expected)));
}

const b64 = (buf) => Buffer.from(buf).toString("base64url");
const mac = (secret, data) => createHmac("sha256", secret).update(data).digest();

export function signSession(secret, now = Date.now()) {
  const payload = b64(JSON.stringify({ exp: Math.floor(now / 1000) + SESSION_SECONDS }));
  return `${payload}.${b64(mac(secret, payload))}`;
}

export function verifySession(secret, token, now = Date.now()) {
  if (typeof token !== "string") return false;
  const [payload, sig, extra] = token.split(".");
  if (!payload || !sig || extra !== undefined) return false;
  const expected = mac(secret, payload);
  let given;
  try { given = Buffer.from(sig, "base64url"); } catch { return false; }
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) return false;
  try {
    const { exp } = JSON.parse(Buffer.from(payload, "base64url").toString());
    return Number.isInteger(exp) && exp * 1000 > now;
  } catch { return false; }
}

export function readCookie(req, name) {
  for (const part of (req.headers.get("cookie") || "").split(";")) {
    const i = part.indexOf("=");
    if (i > 0 && part.slice(0, i).trim() === name) return part.slice(i + 1).trim();
  }
  return null;
}

export function sessionCookie(req, value, maxAge) {
  const secure = new URL(req.url).protocol === "https:" ? "; Secure" : "";
  return `${COOKIE}=${value}; Path=/api/admin; HttpOnly; SameSite=Strict; Max-Age=${maxAge}${secure}`;
}

export const hashIp = (secret, ip) => createHmac("sha256", secret).update(String(ip || "unknown")).digest("hex").slice(0, 32);
