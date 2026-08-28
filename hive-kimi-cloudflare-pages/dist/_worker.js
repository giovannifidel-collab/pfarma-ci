const TASK_ID = "HIVE-KIMI-PAGES-0004";
const LAB_NONCE = "HIVE-KIMI-CF-PAGES-20260828-V1";
const EXPECTED_ANSWER = "768";
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
    try {
      const url = new URL(request.url);

      if (request.method !== "GET") {
        return json({ ok: false, error: "method_not_allowed" }, 405);
      }

      if (url.pathname === "/health") {
        return json({
          ok: true,
          service: "hive-kimi-cloudflare-pages",
          version: "1.0",
          transport: "cloudflare-pages",
        });
      }

      if (url.pathname === "/work") {
        return json({
          hive: "HIVE Kimi Stable Relay",
          version: "1.0-pages",
          task_id: TASK_ID,
          agent: "KIMI_CHAT_FREE",
          purpose: "Certify a real HIVE task roundtrip through a stable Cloudflare Pages endpoint.",
          task: {
            type: "arithmetic",
            expression: "(48 * 17) + (225 / 15) - 63",
            output: "Return only the integer result as answer in the callback URL.",
          },
          instructions: [
            "Use web_open_url to read this task.",
            "Compute the arithmetic expression yourself.",
            "Open exactly one callback URL built from callback_template by replacing <ANSWER> with your integer result.",
            "Do not use GitHub, Kimi Code, MCP, API keys, localhost, or paid tools.",
            "After the callback, report the task_id, computed answer, and callback response to the user.",
          ],
          callback_template: `${url.origin}/work-submit?task_id=${encodeURIComponent(TASK_ID)}&nonce=${encodeURIComponent(LAB_NONCE)}&answer=<ANSWER>`,
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
            next: "HIVE already certified this Kimi Pages result.",
          });
        }

        const record = {
          certified: true,
          task_id: TASK_ID,
          answer: EXPECTED_ANSWER,
          transport: "cloudflare-pages",
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
          next: "Report HIVE KIMI PAGES READY to the user.",
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

      if (url.pathname === "/") {
        return json({
          ok: true,
          service: "HIVE Kimi Cloudflare Pages Relay",
          work: `${url.origin}/work`,
          result: `${url.origin}/work-result`,
        });
      }

      return json({ ok: false, error: "not_found" }, 404);
    } catch (error) {
      return json({
        ok: false,
        error: "pages_runtime_exception",
        message: error instanceof Error ? error.message : String(error),
      }, 500);
    }
  },
};
