import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";
import { chmod, mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

const command = process.argv[2];
const supabaseUrl = required("SUPABASE_URL").replace(/\/$/, "");
const serviceKey = required("SUPABASE_SERVICE_ROLE_KEY");
const codexHome = required("CODEX_HOME");
const objectPath = "codex-auth/state.json";

function required(name) {
  const value = process.env[name];
  if (!value) throw new Error(`Missing ${name}`);
  return value;
}

function stateKey() {
  const raw = required("CODEX_AUTH_STATE_KEY_B64");
  const key = Buffer.from(raw, "base64");
  if (key.length !== 32) throw new Error(`CODEX_AUTH_STATE_KEY_B64 decodes to ${key.length} bytes; expected 32`);
  return key;
}

function encodedPath(path) {
  return path.split("/").map(encodeURIComponent).join("/");
}

function uploadObjectUrl(path) {
  return `${supabaseUrl}/storage/v1/object/preparatore-v2-worker-state/${encodedPath(path)}`;
}

function downloadObjectUrl(path) {
  return `${supabaseUrl}/storage/v1/object/authenticated/preparatore-v2-worker-state/${encodedPath(path)}`;
}

function containsRefreshToken(value) {
  if (!value || typeof value !== "object") return false;
  for (const [key, item] of Object.entries(value)) {
    if (key === "refresh_token" && typeof item === "string" && item.length > 20) return true;
    if (containsRefreshToken(item)) return true;
  }
  return false;
}

function validateAuth(text, source = "auth state") {
  if (Buffer.byteLength(text, "utf8") > 64 * 1024) throw new Error(`${source} is too large`);
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error(`${source} is not valid JSON`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(`${source} is not a JSON object`);
  if (!containsRefreshToken(parsed)) throw new Error(`${source} has no ChatGPT refresh token`);
  if ("auth_mode" in parsed && parsed.auth_mode !== "chatgpt") throw new Error(`${source} is not ChatGPT-managed`);
  return text;
}

function seedAuth() {
  const seed = required("CODEX_AUTH_SEED_B64");
  const decoded = Buffer.from(seed, "base64").toString("utf8");
  return validateAuth(decoded, "CODEX_AUTH_SEED_B64");
}

function encrypt(text) {
  const key = stateKey();
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const ciphertext = Buffer.concat([cipher.update(text, "utf8"), cipher.final()]);
  return JSON.stringify({ v: 1, iv: iv.toString("base64"), tag: cipher.getAuthTag().toString("base64"), ciphertext: ciphertext.toString("base64") });
}

function decrypt(text) {
  const key = stateKey();
  const value = JSON.parse(text);
  if (value?.v !== 1) throw new Error("Unsupported encrypted auth state");
  const decipher = createDecipheriv("aes-256-gcm", key, Buffer.from(value.iv, "base64"));
  decipher.setAuthTag(Buffer.from(value.tag, "base64"));
  return Buffer.concat([decipher.update(Buffer.from(value.ciphertext, "base64")), decipher.final()]).toString("utf8");
}

async function restore() {
  const response = await fetch(downloadObjectUrl(objectPath), {
    headers: { Authorization: `Bearer ${serviceKey}`, apikey: serviceKey },
    cache: "no-store",
  });
  let plaintext;
  if (response.ok) {
    try {
      plaintext = validateAuth(decrypt(await response.text()), "stored ChatGPT auth state");
      process.stdout.write("Stored ChatGPT auth state validated.\n");
    } catch (error) {
      process.stdout.write(`Stored auth unavailable (${error instanceof Error ? error.message : "unknown"}); trying trusted seed.\n`);
      plaintext = seedAuth();
      process.stdout.write("Trusted ChatGPT auth seed validated.\n");
    }
  } else if (response.status === 404) {
    plaintext = seedAuth();
    process.stdout.write("No stored auth state; trusted ChatGPT auth seed validated.\n");
  } else {
    throw new Error(`Unable to restore auth state (${response.status})`);
  }
  await mkdir(codexHome, { recursive: true, mode: 0o700 });
  const authPath = join(codexHome, "auth.json");
  await writeFile(authPath, plaintext, { mode: 0o600 });
  await chmod(authPath, 0o600);
  process.stdout.write("ChatGPT auth state restored securely.\n");
}

async function persist() {
  const plaintext = validateAuth(await readFile(join(codexHome, "auth.json"), "utf8"), "refreshed ChatGPT auth state");
  const response = await fetch(uploadObjectUrl(objectPath), {
    method: "POST",
    headers: { Authorization: `Bearer ${serviceKey}`, apikey: serviceKey, "Content-Type": "application/json", "x-upsert": "true" },
    body: encrypt(plaintext),
  });
  if (!response.ok) throw new Error(`Unable to persist auth state (${response.status})`);
  process.stdout.write("Updated ChatGPT auth state persisted securely.\n");
}

if (command === "restore") await restore();
else if (command === "persist") await persist();
else throw new Error("Usage: codex-auth-state.mjs restore|persist");
