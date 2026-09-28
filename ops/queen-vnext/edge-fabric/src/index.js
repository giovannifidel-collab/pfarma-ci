function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" }
  });
}

function textFromResult(result) {
  if (typeof result === "string") return result;
  if (typeof result?.response === "string") return result.response;
  const content = result?.choices?.[0]?.message?.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content.map((part) => part?.text || "").join("").trim();
  }
  return "";
}

function familyFromModel(model) {
  const path = model.replace(/^@cf\//, "");
  const [vendor = "unknown", raw = "unknown"] = path.split("/");
  const family = raw.split("-").slice(0, 3).join("-");
  return `${vendor}/${family}`;
}

function safeAiError(error) {
  const safe = {
    name: String(error?.name || "Error").slice(0, 120),
    code: error?.code == null ? null : String(error.code).slice(0, 120),
    message: String(error?.message || "").slice(0, 500)
  };
  return safe;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return json({
        status: "ok",
        service: "hive-queen-ai-fabric",
        runtime: env.HIVE_RUNTIME_MODE || "unknown",
        capability: "hive.ai.general",
        event_driven: true,
        scheduled_dependency: false
      });
    }

    if (request.method !== "POST" || url.pathname !== "/run") {
      return json({ status: "error", error: "not_found" }, 404);
    }

    let input;
    try {
      input = await request.json();
    } catch {
      return json({ status: "error", error: "invalid_json" }, 400);
    }

    const task = String(input?.task || "").trim();
    const model = String(input?.model || "@cf/zai-org/glm-4.7-flash").trim();
    const eventId = String(input?.event_id || crypto.randomUUID());

    if (!task) return json({ status: "error", error: "task_required" }, 400);
    if (!model.startsWith("@cf/")) {
      return json({ status: "error", error: "zero_cost_first_workers_ai_only" }, 400);
    }

    const started = Date.now();
    try {
      const result = await env.AI.run(
        model,
        {
          prompt: [
            "You are a HIVE execution backend.",
            "Follow the task exactly.",
            "Return only the direct task result unless an explanation is explicitly requested.",
            "TASK:",
            task
          ].join("\n")
        },
        {
          gateway: {
            id: "default",
            skipCache: true,
            collectLog: true,
            metadata: {
              hive_capability: "hive.ai.general",
              hive_event_id: eventId,
              hive_transport: "cloudflare-worker-ai-binding"
            }
          }
        }
      );

      const text = textFromResult(result).trim();
      if (!text) {
        return json({
          status: "error",
          text: "",
          metadata: {
            capability: "hive.ai.general",
            provider: "cloudflare-workers-ai",
            model,
            model_family: familyFromModel(model),
            independence_group: model.replace(/^@cf\//, ""),
            transport: "cloudflare-worker-ai-binding",
            gateway: "default",
            route_id: `workers-ai-binding:${model}`,
            source: "pfarma-ci-public",
            enrollment: "candidate",
            certified: false,
            event_id: eventId,
            latency_ms: Date.now() - started,
            gateway_log_id: env.AI.aiGatewayLogId || null,
            error: "empty_model_response"
          }
        }, 502);
      }

      return json({
        status: "ok",
        text,
        metadata: {
          capability: "hive.ai.general",
          provider: "cloudflare-workers-ai",
          model,
          model_family: familyFromModel(model),
          independence_group: model.replace(/^@cf\//, ""),
          transport: "cloudflare-worker-ai-binding",
          gateway: "default",
          route_id: `workers-ai-binding:${model}`,
          source: "pfarma-ci-public",
          enrollment: "candidate",
          certified: false,
          event_id: eventId,
          latency_ms: Date.now() - started,
          gateway_log_id: env.AI.aiGatewayLogId || null
        }
      });
    } catch (error) {
      const diagnostic = safeAiError(error);
      console.error("AI_BINDING_ERROR", JSON.stringify(diagnostic));
      return json({
        status: "error",
        text: "",
        metadata: {
          capability: "hive.ai.general",
          provider: "cloudflare-workers-ai",
          model,
          model_family: familyFromModel(model),
          independence_group: model.replace(/^@cf\//, ""),
          transport: "cloudflare-worker-ai-binding",
          gateway: "default",
          route_id: `workers-ai-binding:${model}`,
          source: "pfarma-ci-public",
          enrollment: "candidate",
          certified: false,
          event_id: eventId,
          latency_ms: Date.now() - started,
          error: "ai_binding_execution_failed",
          error_name: diagnostic.name,
          error_code: diagnostic.code,
          error_message: diagnostic.message
        }
      }, 502);
    }
  }
};
