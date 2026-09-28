#!/usr/bin/env node

const ACCOUNT_ID = process.env.HIVE_CF_ACCOUNT_ID;
const API_TOKEN = process.env.HIVE_CF_AIG_TOKEN;
const GATEWAY_ID = process.env.HIVE_CF_GATEWAY_ID || 'default';

function fail(message, code = 1, metadata = {}) {
  process.stdout.write(JSON.stringify({
    status: 'error',
    text: '',
    metadata: {
      error: message,
      provider: 'cloudflare-workers-ai',
      transport: 'https',
      route: 'cloudflare.ai.run.model_path',
      gateway: GATEWAY_ID,
      paid_fallback: false,
      ...metadata
    }
  }));
  process.exit(code);
}

function configForRole(role) {
  if (role === 'verifier') {
    return {
      model: process.env.HIVE_VERIFIER_MODEL || '@cf/qwen/qwen2.5-coder-32b-instruct',
      model_family: 'qwen',
      independence_group: 'qwen'
    };
  }
  return {
    model: process.env.HIVE_WORKER_MODEL || '@cf/meta/llama-3.1-8b-instruct-fp8',
    model_family: 'meta-llama',
    independence_group: 'meta-llama'
  };
}

function parseArgs() {
  const raw = process.env.HIVE_AGENT_INPUT || process.argv[2];
  if (!raw) fail('missing_input', 10);
  try {
    const input = JSON.parse(raw);
    if (!input || typeof input !== 'object') fail('invalid_input', 11);
    if (!input.task || typeof input.task !== 'string') fail('missing_task', 12);
    const role = input.role === 'verifier' ? 'verifier' : 'worker';
    return { ...input, role };
  } catch {
    fail('invalid_json', 13);
  }
}

function extractText(body) {
  const result = body?.result;
  const candidates = [
    result?.response,
    result?.choices?.[0]?.message?.content,
    body?.response,
    body?.choices?.[0]?.message?.content,
    typeof result === 'string' ? result : null
  ];
  return candidates.find((value) => typeof value === 'string' && value.length > 0) || null;
}

async function run() {
  if (!ACCOUNT_ID) fail('missing_account_id', 20);
  if (!API_TOKEN) fail('missing_api_token', 21);

  const input = parseArgs();
  const cfg = configForRole(input.role);
  const started = Date.now();
  const messages = [];
  if (input.system) messages.push({ role: 'system', content: String(input.system) });
  messages.push({ role: 'user', content: input.task });

  let response;
  try {
    response = await fetch(`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/ai/run/${cfg.model}`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${API_TOKEN}`,
        'Content-Type': 'application/json',
        'cf-aig-gateway-id': GATEWAY_ID
      },
      body: JSON.stringify({
        messages,
        temperature: input.temperature ?? 0,
        max_tokens: input.max_tokens ?? 512,
        stream: false
      })
    });
  } catch (error) {
    fail('transport_error', 30, { detail: String(error?.message || error), ...cfg });
  }

  const latency_ms = Date.now() - started;
  const rawText = await response.text();
  let body;
  try {
    body = JSON.parse(rawText);
  } catch {
    fail('non_json_response', 31, { http_status: response.status, latency_ms, ...cfg });
  }

  if (!response.ok || body?.success === false) {
    fail('upstream_http_error', 32, {
      http_status: response.status,
      latency_ms,
      upstream_errors: body?.errors || null,
      ...cfg
    });
  }

  const text = extractText(body);
  if (!text) {
    fail('missing_model_text', 33, {
      http_status: response.status,
      latency_ms,
      response_shape: {
        top_level: body && typeof body === 'object' ? Object.keys(body) : [],
        result_type: Array.isArray(body?.result) ? 'array' : typeof body?.result,
        result_keys: body?.result && typeof body.result === 'object' && !Array.isArray(body.result) ? Object.keys(body.result) : []
      },
      ...cfg
    });
  }

  const usage = body?.result?.usage ?? body?.usage ?? null;
  process.stdout.write(JSON.stringify({
    status: 'ok',
    text,
    metadata: {
      provider: 'cloudflare-workers-ai',
      model: cfg.model,
      model_family: cfg.model_family,
      independence_group: cfg.independence_group,
      transport: 'https',
      route: 'cloudflare.ai.run.model_path',
      gateway: GATEWAY_ID,
      latency_ms,
      http_status: response.status,
      usage,
      paid_fallback: false,
      role: input.role
    }
  }));
}

run().catch((error) => fail('unhandled_error', 99, { detail: String(error?.message || error) }));
