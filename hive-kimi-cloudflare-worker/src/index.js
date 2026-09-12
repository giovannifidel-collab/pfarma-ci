const TASK_ID = "HIVE-KIMI-WORK-0004";
const LAB_NONCE = "HIVE-KIMI-CF-JINA-20260828-V2";
const EXPECTED_ANSWER = "21246";
const RESULT_KEY = `result:${TASK_ID}`;

const STRESS_ID = "HIVE-KIMI-STRESS-0005";
const STRESS_NONCE = "HIVE-KIMI-STRESS-JINA-20260828-V1";
const STRESS_EXPECTED = "138460";
const STRESS_RESULT_KEY = `result:${STRESS_ID}`;

const JINA_READER_PREFIX = "https://r.jina.ai/";

function json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "access-control-allow-origin": "*",
    },
  });
}

function readerUrl(originUrl) {
  return `${JINA_READER_PREFIX}${originUrl}`;
}

async function acceptAnswer(request, env, taskId, nonce, answer) {
  const normalizedAnswer = String(answer || "").trim();

  if (taskId !== TASK_ID || nonce !== LAB_NONCE) {
    return json({ ok: false, accepted: false, certified: false, error: "invalid_task_or_nonce" }, 400);
  }

  if (normalizedAnswer !== EXPECTED_ANSWER) {
    return json({
      ok: true,
      accepted: false,
      certified: false,
      task_id: TASK_ID,
      answer: normalizedAnswer,
      error: "wrong_answer",
    });
  }

  const existing = await env.HIVE_KIMI_RESULTS.get(RESULT_KEY, "json");
  if (existing?.certified === true) {
    return json({
      ok: true,
      accepted: true,
      certified: true,
      duplicate: true,
      task_id: TASK_ID,
      answer: EXPECTED_ANSWER,
      bridge: "jina-reader",
      message: "HIVE KIMI JINA ROUNDTRIP READY",
    });
  }

  const record = {
    certified: true,
    task_id: TASK_ID,
    answer: EXPECTED_ANSWER,
    bridge: "jina-reader",
    received_at: new Date().toISOString(),
    user_agent: request.headers.get("user-agent"),
    cf_ray: request.headers.get("cf-ray"),
  };

  await env.HIVE_KIMI_RESULTS.put(RESULT_KEY, JSON.stringify(record));

  return json({
    ok: true,
    accepted: true,
    certified: true,
    duplicate: false,
    task_id: TASK_ID,
    answer: EXPECTED_ANSWER,
    bridge: "jina-reader",
    message: "HIVE KIMI JINA ROUNDTRIP READY",
  });
}

async function acceptStressAnswer(request, env, taskId, nonce, answer) {
  const normalizedAnswer = String(answer || "").trim();

  if (taskId !== STRESS_ID || nonce !== STRESS_NONCE) {
    return json({ ok: false, accepted: false, certified: false, error: "invalid_stress_task_or_nonce" }, 400);
  }

  if (normalizedAnswer !== STRESS_EXPECTED) {
    return json({
      ok: true,
      accepted: false,
      certified: false,
      task_id: STRESS_ID,
      answer: normalizedAnswer,
      error: "wrong_stress_checksum",
    });
  }

  const existing = await env.HIVE_KIMI_RESULTS.get(STRESS_RESULT_KEY, "json");
  if (existing?.certified === true) {
    return json({
      ok: true,
      accepted: true,
      certified: true,
      duplicate: true,
      task_id: STRESS_ID,
      answer: STRESS_EXPECTED,
      bridge: "jina-reader",
      test: "multi-shard",
      message: "HIVE KIMI MULTI-SHARD STRESS READY",
    });
  }

  const record = {
    certified: true,
    task_id: STRESS_ID,
    answer: STRESS_EXPECTED,
    bridge: "jina-reader",
    test: "multi-shard",
    shard_count: 3,
    received_at: new Date().toISOString(),
    user_agent: request.headers.get("user-agent"),
    cf_ray: request.headers.get("cf-ray"),
  };

  await env.HIVE_KIMI_RESULTS.put(STRESS_RESULT_KEY, JSON.stringify(record));

  return json({
    ok: true,
    accepted: true,
    certified: true,
    duplicate: false,
    task_id: STRESS_ID,
    answer: STRESS_EXPECTED,
    bridge: "jina-reader",
    test: "multi-shard",
    message: "HIVE KIMI MULTI-SHARD STRESS READY",
  });
}

const STRESS_SHARDS = {
  alpha: {
    shard_id: "alpha",
    expression: "(731 * 29) + 47",
    instruction: "Compute the integer value of expression and retain it as alpha.",
  },
  beta: {
    shard_id: "beta",
    expression: "(1257 * 43) - 918",
    instruction: "Compute the integer value of expression and retain it as beta.",
  },
  gamma: {
    shard_id: "gamma",
    expression: "(98765 - 43210) + (144 * 17)",
    instruction: "Compute the integer value of expression and retain it as gamma.",
  },
};

export default {
  async fetch(request, env) {
    if (request.method === "GET" && request.url.endsWith("/health")) {
      return new Response('{"ok":true,"service":"hive-kimi-cloudflare-worker","version":"1.3","transport":"cloudflare-workers","jina_bridge":true,"stress_test":"HIVE-KIMI-STRESS-0005"}', {
        status: 200,
        headers: {
          "content-type": "application/json; charset=utf-8",
          "cache-control": "no-store",
          "access-control-allow-origin": "*",
        },
      });
    }

    try {
      const url = new URL(request.url);

      if (request.method !== "GET") {
        return json({ ok: false, error: "method_not_allowed" }, 405);
      }

      const workPath = `/work/${TASK_ID}`;
      if (url.pathname === "/work" || url.pathname === workPath) {
        const originCallbackTemplate = `${url.origin}/work-submit/${encodeURIComponent(TASK_ID)}/${encodeURIComponent(LAB_NONCE)}/<ANSWER>`;
        const originResultUrl = `${url.origin}/work-result/${encodeURIComponent(TASK_ID)}`;

        return json({
          hive: "HIVE Kimi Stable Relay",
          version: "1.3",
          task_id: TASK_ID,
          agent: "KIMI_CHAT_FREE",
          transport: {
            backend: "cloudflare-workers",
            compatibility_bridge: "jina-reader",
            api_key_required: false,
          },
          purpose: "Certify an operational HIVE-to-Kimi-to-HIVE task roundtrip while using Jina Reader only as a compatibility bridge to the Cloudflare Worker.",
          task: {
            type: "arithmetic",
            expression: "(731 * 29) + 47",
            output: "Return only the integer result by replacing <ANSWER> in callback_template.",
          },
          instructions: [
            "Compute the arithmetic expression yourself.",
            "Take callback_template exactly as provided and replace <ANSWER> with the integer result.",
            "Open that resulting callback URL exactly once with web_open_url.",
            "The callback_template already uses the Jina Reader bridge; do not remove or modify the r.jina.ai prefix.",
            "Do not open origin_callback_template directly.",
            "Do not use GitHub, Kimi Code, MCP, API keys, localhost, Python requests, or paid tools.",
            "After the callback, report task_id, computed answer, callback URL, whether accepted/certified, and the callback response.",
            "If web_open_url reports an error after attempting the callback, do not retry the callback; report the exact error.",
          ],
          callback_template: readerUrl(originCallbackTemplate),
          origin_callback_template: originCallbackTemplate,
          result_url: originResultUrl,
          reader_result_url: readerUrl(originResultUrl),
          security: {
            lab_only: true,
            production_data: false,
            secrets_required: false,
            nonce_is_correlation_only: true,
            idempotent: true,
          },
        });
      }

      const stressMasterPath = `/stress/${STRESS_ID}`;
      if (url.pathname === "/stress" || url.pathname === stressMasterPath) {
        const shardUrls = Object.keys(STRESS_SHARDS).map((shardId) => ({
          shard_id: shardId,
          url: readerUrl(`${url.origin}/stress/${encodeURIComponent(STRESS_ID)}/shard/${encodeURIComponent(shardId)}`),
        }));
        const originCallbackTemplate = `${url.origin}/stress-submit/${encodeURIComponent(STRESS_ID)}/${encodeURIComponent(STRESS_NONCE)}/<ANSWER>`;
        const originResultUrl = `${url.origin}/stress-result/${encodeURIComponent(STRESS_ID)}`;

        return json({
          hive: "HIVE Kimi Multi-Shard Stress Relay",
          version: "1.0",
          task_id: STRESS_ID,
          agent: "KIMI_CHAT_FREE",
          test_kind: "multi-fetch-single-callback",
          purpose: "Test whether one started Kimi execution can perform several consecutive HIVE reads, maintain intermediate state, compute a final checksum, and return one certified callback without human intervention between steps.",
          shard_urls: shardUrls,
          combine: {
            formula: "alpha + beta + gamma + 6078",
            output: "Use the resulting integer as <ANSWER> in callback_template.",
          },
          instructions: [
            "Open each shard URL exactly once with web_open_url, in the order alpha, beta, gamma.",
            "For each shard, compute the integer expression and retain the value under its shard_id.",
            "After all three shards are complete, compute final checksum using combine.formula.",
            "Replace only <ANSWER> in callback_template with that final integer checksum.",
            "Open the resulting callback URL exactly once with web_open_url.",
            "Do not ask the user for help between shard reads.",
            "Do not use Python, requests, GitHub, Kimi Code, MCP, API keys, localhost, or paid tools.",
            "If a shard fetch or callback fails, do not repeat it; report the exact failing step and error.",
            "At the end report alpha, beta, gamma, final checksum, callback URL, accepted, certified, duplicate, and complete callback response.",
          ],
          callback_template: readerUrl(originCallbackTemplate),
          origin_callback_template: originCallbackTemplate,
          result_url: originResultUrl,
          reader_result_url: readerUrl(originResultUrl),
          security: {
            lab_only: true,
            production_data: false,
            secrets_required: false,
            nonce_is_correlation_only: true,
            idempotent: true,
          },
        });
      }

      const stressShardPrefix = `/stress/${STRESS_ID}/shard/`;
      if (url.pathname.startsWith(stressShardPrefix)) {
        const shardId = decodeURIComponent(url.pathname.slice(stressShardPrefix.length));
        const shard = STRESS_SHARDS[shardId];
        if (!shard) {
          return json({ ok: false, error: "stress_shard_not_found", shard_id: shardId }, 404);
        }
        return json({
          ok: true,
          task_id: STRESS_ID,
          ...shard,
        });
      }

      // Preferred path-based callback for certified task 0004.
      const parts = url.pathname.split("/").filter(Boolean);
      if (parts[0] === "work-submit" && parts.length === 4) {
        const taskId = decodeURIComponent(parts[1]);
        const nonce = decodeURIComponent(parts[2]);
        const answer = decodeURIComponent(parts[3]);
        return await acceptAnswer(request, env, taskId, nonce, answer);
      }

      // Stress-test path callback.
      if (parts[0] === "stress-submit" && parts.length === 4) {
        const taskId = decodeURIComponent(parts[1]);
        const nonce = decodeURIComponent(parts[2]);
        const answer = decodeURIComponent(parts[3]);
        return await acceptStressAnswer(request, env, taskId, nonce, answer);
      }

      // Legacy query callback retained only for compatibility with earlier lab runs.
      if (url.pathname === "/work-submit") {
        return await acceptAnswer(
          request,
          env,
          url.searchParams.get("task_id") || "",
          url.searchParams.get("nonce") || "",
          url.searchParams.get("answer") || "",
        );
      }

      if (url.pathname === "/work-result" || url.pathname === `/work-result/${TASK_ID}`) {
        const record = await env.HIVE_KIMI_RESULTS.get(RESULT_KEY, "json");
        return json({
          ok: true,
          task_id: TASK_ID,
          certified: record?.certified === true,
          bridge: "jina-reader",
          result: record || null,
        });
      }

      if (url.pathname === "/stress-result" || url.pathname === `/stress-result/${STRESS_ID}`) {
        const record = await env.HIVE_KIMI_RESULTS.get(STRESS_RESULT_KEY, "json");
        return json({
          ok: true,
          task_id: STRESS_ID,
          certified: record?.certified === true,
          bridge: "jina-reader",
          test: "multi-shard",
          result: record || null,
        });
      }

      return json({ ok: false, error: "not_found" }, 404);
    } catch (error) {
      return json({
        ok: false,
        error: "worker_runtime_exception",
        message: error instanceof Error ? error.message : String(error),
      }, 500);
    }
  },
};
