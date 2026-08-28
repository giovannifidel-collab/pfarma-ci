const TASK_ID = "HIVE-KIMI-WORK-0003";
const LAB_NONCE = "HIVE-KIMI-CF-WORK-20260828-V1";
const EXPECTED_ANSWER = "657";
const RESULT_KEY = `result:${TASK_ID}`;

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

export default {
  async fetch(request, env) {
    // Deliberately minimal health path: no KV, no URL parsing, no external calls.
    // If this still returns a Cloudflare-generated 500, the failure is outside
    // the application handler (workers.dev/account/routing level).
    if (request.method === "GET" && request.url.endsWith("/health")) {
      return new Response('{"ok":true,"service":"hive-kimi-cloudflare-worker","version":"1.1","transport":"cloudflare-workers"}', {
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

      if (url.pathname === "/work") {
        const callbackBase = `${url.origin}/work-submit`;
        return json({
          hive: "HIVE Kimi Stable Relay",
          version: "1.1",
          task_id: TASK_ID,
          agent: "KIMI_CHAT_FREE",
          purpose: "Certify that Kimi can read a HIVE task, solve it, and return the computed result to HIVE over a stable Cloudflare Worker endpoint.",
          task: {
            type: "arithmetic",
            expression: "(37 * 19) + (144 / 12) - 58",
            output: "Return only the integer result as answer in the callback URL.",
          },
          instructions: [
            "Use web_open_url to read this task.",
            "Compute the arithmetic expression yourself.",
            "Open exactly one callback URL built from callback_template by replacing <ANSWER> with your integer result.",
            "Do not use GitHub, Kimi Code, MCP, API keys, localhost, or paid tools.",
            "After the callback, report the task_id, computed answer, and callback response to the user.",
          ],
          callback_template: `${callbackBase}?task_id=${encodeURIComponent(TASK_ID)}&nonce=${encodeURIComponent(LAB_NONCE)}&answer=<ANSWER>`,
          result_url: `${url.origin}/work-result`,
          security: {
            lab_only: true,
            production_data: false,
            secrets_required: false,
            idempotent: true,
          },
        });
      }

      if (url.pathname === "/work-submit") {
        const taskId = url.searchParams.get("task_id") || "";
        const nonce = url.searchParams.get("nonce") || "";
        const answer = (url.searchParams.get("answer") || "").trim();

        if (taskId !== TASK_ID || nonce !== LAB_NONCE) {
          return json({ ok: false, accepted: false, error: "invalid_task_or_nonce" }, 400);
        }

        if (answer !== EXPECTED_ANSWER) {
          return json({
            ok: true,
            accepted: false,
            certified: false,
            task_id: TASK_ID,
            answer,
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
            next: "HIVE already certified this Kimi result.",
          });
        }

        const record = {
          certified: true,
          task_id: TASK_ID,
          answer: EXPECTED_ANSWER,
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
          next: "Report HIVE KIMI WORKER READY to the user.",
        });
      }

      if (url.pathname === "/work-result") {
        const record = await env.HIVE_KIMI_RESULTS.get(RESULT_KEY, "json");
        return json({
          ok: true,
          task_id: TASK_ID,
          certified: record?.certified === true,
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
