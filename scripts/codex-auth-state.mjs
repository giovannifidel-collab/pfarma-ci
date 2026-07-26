import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";
import { chmod, mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

const command = process.argv[2];
const supabaseUrl = required("SUPABASE_URL").replace(/\/$/, "");
const serviceKey = required("SUPABASE_SERVICE_ROLE_KEY");
const codexHome = required("CODEX_HOME");
const stateKey = Buffer.from(required("CODEX_AUTH_STATE_KEY_B64"), "base64");
const objectPath = "codex-auth/state.json";
if (stateKey.length !== 32) throw new Error("CODEX_AUTH_STATE_KEY_B64 must decode to 32 bytes");

function required(name) {
  const value = process.env[name];
  if (!value) throw new Error(`Missing ${name}`);
  return value;
}

function objectUrl(path) {
  return `${supabaseUrl}/storage/v1/object/preparatore-v2-worker-state/${path.split("/").map(encodeURIComponent).join("/")}`;
}

function containsRefreshToken(value) {
  if (!value || typeof value !== "object") return false;
  for (const [key, item] of Object.entries(value)) {
    if (key === "refresh_token" && typeof item === "string" && item.length > 20) return true;
    if (containsRefreshToken(item)) return true;
  }
  return false;
}

function validateAuth(text) {
  if (Buffer.byteLength(text, "utf8") > 64 * 1024) throw new Error("Auth state too large");
  const parsed = JSON.parse(text);
  if (!parsed || typeof parsed !== "object" || !containsRefreshToken(parsed)) throw new Error("Invalid ChatGPT auth state");
  if ("auth_mode" in parsed && parsed.auth_mode !== "chatgpt") throw new Error("Auth state is not ChatGPT-managed");
  return text;
}

function seedAuth() {
  const seed = process.env.CODEX_AUTH_SEED_B64;
  if (!seed) throw new Error("Missing CODEX_AUTH_SEED_B64");
  return validateAuth(Buffer.from(seed, "base64").toString("utf8"));
}

function encrypt(text) {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", stateKey, iv);
  const ciphertext = Buffer.concat([cipher.update(text, "utf8"), cipher.final()]);
  return JSON.stringify({ v: 1, iv: iv.toString("base64"), tag: cipher.getAuthTag().toString("base64"), ciphertext: ciphertext.toString("base64") });
}

function decrypt(text) {
  const value = JSON.parse(text);
  if (value?.v !== 1) throw new Error("Unsupported encrypted auth state");
  const decipher = createDecipheriv("aes-256-gcm", stateKey, Buffer.from(value.iv, "base64"));
  decipher.setAuthTag(Buffer.from(value.tag, "base64"));
  return Buffer.concat([decipher.update(Buffer.from(value.ciphertext, "base64")), decipher.final()]).toString("utf8");
}

async function restore() {
  const response = await fetch(objectUrl(objectPath), { headers: { Authorization: `Bearer ${serviceKey}`, apikey: serviceKey }, cache: "no-store" });
  let plaintext;
  if (response.ok) {
    try {
      plaintext = validateAuth(decrypt(await response.text()));
    } catch {
      plaintext = seedAuth();
      process.stdout.write("Stored ChatGPT auth state unavailable; trusted seed restored.\n");
    }
  } else if (response.status === 404) {
    plaintext = seedAuth();
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
  const plaintext = validateAuth(await readFile(join(codexHome, "auth.json"), "utf8"));
  const response = await fetch(objectUrl(objectPath), {
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
