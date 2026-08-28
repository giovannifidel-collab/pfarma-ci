const OIDC_ISSUER = "https://token.actions.githubusercontent.com";
const OIDC_JWKS_URL = "https://token.actions.githubusercontent.com/.well-known/jwks";
const OIDC_AUDIENCE = "hive-kimi-dispatcher";
const ALLOWED_REPOSITORY = "giovannifidel-collab/pfarma-ci";
const ALLOWED_REF = "refs/heads/hive-kimi-dispatcher-v0";
const ALLOWED_WORKFLOW_REF = "giovannifidel-collab/pfarma-ci/.github/workflows/hive-kimi-dispatcher.yml@refs/heads/hive-kimi-dispatcher-v0";
export const KIMI_SESSION_KEY = "session:kimi:storage-state-gz-b64";

function b64urlToBytes(value) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, c => c.charCodeAt(0));
}

function decodePart(value) {
  return JSON.parse(new TextDecoder().decode(b64urlToBytes(value)));
}

function audienceMatches(aud) {
  if (typeof aud === "string") return aud === OIDC_AUDIENCE;
  return Array.isArray(aud) && aud.includes(OIDC_AUDIENCE);
}

export async function verifyGithubActionsOidc(jwt) {
  const parts = String(jwt || "").split(".");
  if (parts.length !== 3) throw new Error("invalid_jwt_shape");

  const [encodedHeader, encodedPayload, encodedSignature] = parts;
  const header = decodePart(encodedHeader);
  const claims = decodePart(encodedPayload);

  if (header.alg !== "RS256" || !header.kid) throw new Error("unsupported_jwt_header");

  const jwksResponse = await fetch(OIDC_JWKS_URL, {
    headers: { "cache-control": "max-age=300" },
  });
  if (!jwksResponse.ok) throw new Error(`jwks_fetch_failed_${jwksResponse.status}`);
  const jwks = await jwksResponse.json();
  const jwk = Array.isArray(jwks.keys) ? jwks.keys.find(k => k.kid === header.kid) : null;
  if (!jwk) throw new Error("matching_jwk_not_found");

  const key = await crypto.subtle.importKey(
    "jwk",
    jwk,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"],
  );

  const signed = new TextEncoder().encode(`${encodedHeader}.${encodedPayload}`);
  const signature = b64urlToBytes(encodedSignature);
  const valid = await crypto.subtle.verify(
    { name: "RSASSA-PKCS1-v1_5" },
    key,
    signature,
    signed,
  );
  if (!valid) throw new Error("invalid_jwt_signature");

  const now = Math.floor(Date.now() / 1000);
  if (claims.iss !== OIDC_ISSUER) throw new Error("invalid_issuer");
  if (!audienceMatches(claims.aud)) throw new Error("invalid_audience");
  if (typeof claims.exp !== "number" || claims.exp < now - 30) throw new Error("token_expired");
  if (typeof claims.nbf === "number" && claims.nbf > now + 30) throw new Error("token_not_yet_valid");
  if (claims.repository !== ALLOWED_REPOSITORY) throw new Error("invalid_repository");
  if (claims.ref !== ALLOWED_REF) throw new Error("invalid_ref");
  if (claims.workflow_ref !== ALLOWED_WORKFLOW_REF) throw new Error("invalid_workflow_ref");

  return claims;
}

export async function serveKimiSessionToDispatcher(request, env) {
  if (request.method !== "GET") {
    return new Response(JSON.stringify({ ok: false, error: "method_not_allowed" }), {
      status: 405,
      headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
    });
  }

  const auth = request.headers.get("authorization") || "";
  const match = auth.match(/^Bearer\s+(.+)$/i);
  if (!match) {
    return new Response(JSON.stringify({ ok: false, error: "missing_bearer_token" }), {
      status: 401,
      headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
    });
  }

  try {
    const claims = await verifyGithubActionsOidc(match[1]);
    const session = await env.HIVE_KIMI_RESULTS.get(KIMI_SESSION_KEY);
    if (!session) {
      return new Response(JSON.stringify({ ok: false, error: "kimi_session_not_bootstrapped" }), {
        status: 503,
        headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
      });
    }

    return new Response(JSON.stringify({
      ok: true,
      format: "gzip-base64-playwright-storage-state",
      session,
      repository: claims.repository,
      ref: claims.ref,
    }), {
      status: 200,
      headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
    });
  } catch (error) {
    return new Response(JSON.stringify({
      ok: false,
      error: "oidc_verification_failed",
      detail: error instanceof Error ? error.message : String(error),
    }), {
      status: 403,
      headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
    });
  }
}
