// Wallura – zentrale Kontenliste
// Konten, die auf PCs mit Wallura angelegt werden, melden sich hier an. Nur der
// Administrator (nach einmaliger Freischaltung) darf die Liste abrufen.
const JSON_HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
};

const NAME_RE = /^[A-Za-z0-9._-]{2,32}$/;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });
}

function clean(value, max) {
  return typeof value === "string" ? value.trim().slice(0, max) : "";
}

async function readJson(request) {
  try {
    const data = await request.json();
    return data && typeof data === "object" ? data : {};
  } catch {
    return {};
  }
}

async function ensureSchema(env) {
  await env.DB.batch([
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS accounts (
      name TEXT NOT NULL COLLATE NOCASE,
      device TEXT NOT NULL,
      platform TEXT NOT NULL DEFAULT '',
      version TEXT NOT NULL DEFAULT '',
      created INTEGER NOT NULL,
      last_seen INTEGER NOT NULL,
      PRIMARY KEY (name, device)
    )`),
    env.DB.prepare("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)"),
  ]);
}

async function sha256(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function ownerHash(env) {
  const row = await env.DB.prepare("SELECT v FROM meta WHERE k = 'owner'").first();
  return row ? row.v : null;
}

async function isOwner(env, request) {
  const header = request.headers.get("Authorization") || "";
  const token = header.startsWith("Bearer ") ? header.slice(7).trim() : "";
  if (!token) return false;
  const owner = await ownerHash(env);
  if (!owner) return false;
  return (await sha256(token)) === owner;
}

async function register(env, request) {
  const body = await readJson(request);
  const name = clean(body.name, 32);
  if (!NAME_RE.test(name)) return json({ error: "invalid_name" }, 400);
  const device = clean(body.device, 64) || "PC";
  const platform = clean(body.platform, 16) || "PC";
  const version = clean(body.version, 16);
  const now = Math.floor(Date.now() / 1000);
  await env.DB.prepare(
    `INSERT INTO accounts (name, device, platform, version, created, last_seen)
     VALUES (?1, ?2, ?3, ?4, ?5, ?5)
     ON CONFLICT(name, device) DO UPDATE SET
       platform = excluded.platform,
       version = excluded.version,
       last_seen = excluded.last_seen`
  )
    .bind(name, device, platform, version, now)
    .run();
  return json({ ok: true });
}

async function claim(env, request) {
  const body = await readJson(request);
  const token = clean(body.token, 128);
  if (token.length < 32) return json({ error: "weak_token" }, 400);
  const hash = await sha256(token);
  const existing = await ownerHash(env);
  if (existing) {
    return existing === hash ? json({ ok: true }) : json({ error: "already_claimed" }, 409);
  }
  await env.DB.prepare("INSERT INTO meta (k, v) VALUES ('owner', ?1) ON CONFLICT(k) DO NOTHING")
    .bind(hash)
    .run();
  return json({ ok: true });
}

async function listAccounts(env, request) {
  if (!(await isOwner(env, request))) return json({ error: "unauthorized" }, 401);
  const { results } = await env.DB.prepare(
    `SELECT name, device, platform, version, created, last_seen
     FROM accounts ORDER BY last_seen DESC LIMIT 500`
  ).all();
  return json({ accounts: results || [] });
}

async function removeAccount(env, request) {
  if (!(await isOwner(env, request))) return json({ error: "unauthorized" }, 401);
  const body = await readJson(request);
  const name = clean(body.name, 32);
  const device = clean(body.device, 64);
  if (!name || !device) return json({ error: "invalid_entry" }, 400);
  await env.DB.prepare("DELETE FROM accounts WHERE name = ?1 AND device = ?2")
    .bind(name, device)
    .run();
  return json({ ok: true });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (url.pathname === "/api/health") {
        return json({ ok: true, service: "wallura-accounts" });
      }
      await ensureSchema(env);
      if (url.pathname === "/api/register" && request.method === "POST") {
        return await register(env, request);
      }
      if (url.pathname === "/api/claim" && request.method === "POST") {
        return await claim(env, request);
      }
      if (url.pathname === "/api/accounts" && request.method === "GET") {
        return await listAccounts(env, request);
      }
      if (url.pathname === "/api/accounts" && request.method === "DELETE") {
        return await removeAccount(env, request);
      }
      return json({ error: "not_found" }, 404);
    } catch (err) {
      return json({ error: "server_error" }, 500);
    }
  },
};
