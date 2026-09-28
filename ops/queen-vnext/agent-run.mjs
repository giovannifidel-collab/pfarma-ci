const token = process.env.HIVE_CF_AIG_TOKEN;
const accountId = process.env.HIVE_CF_ACCOUNT_ID;
const task = (process.env.HIVE_TASK || '').trim();
const model = (process.env.HIVE_MODEL || '@cf/moonshotai/kimi-k2.6').trim();
const eventId = (process.env.HIVE_EVENT_ID || `evt-${Date.now()}`).trim();

if (!token) throw new Error('HIVE_CF_AIG_TOKEN missing');
if (!accountId) throw new Error('HIVE_CF_ACCOUNT_ID missing');
if (!task) throw new Error('HIVE_TASK missing');
if (!model.startsWith('@cf/')) throw new Error('Only Workers AI @cf/ models are allowed in zero-cost-first mode');

const started = Date.now();
const endpoint = `https://api.cloudflare.com/client/v4/accounts/${accountId}/ai/v1/chat/completions`;
const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 90000);

let response;
let body;
try {
  response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'cf-aig-gateway-id': 'default',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model,
      messages: [
        {
          role: 'system',
          content: 'You are a HIVE execution backend. Follow the task exactly. Return only the direct task result unless the task explicitly asks for explanation.'
        },
        { role: 'user', content: task }
      ],
      temperature: 0,
      max_tokens: 512
    }),
    signal: controller.signal
  });
  body = await response.json();
} finally {
  clearTimeout(timeout);
}

const latencyMs = Date.now() - started;
const cfRay = response.headers.get('cf-ray') || null;

if (!response.ok) {
  const errorResult = {
    status: 'error',
    text: '',
    metadata: {
      capability: 'hive.ai.general',
      provider: 'cloudflare-workers-ai',
      model,
      model_family: model.replace(/^@cf\//, '').split('/').slice(0, 2).join('/'),
      independence_group: model.replace(/^@cf\//, ''),
      transport: 'cloudflare-ai-gateway-rest',
      gateway: 'default',
      route_id: `workers-ai:${model}`,
      source: 'pfarma-ci-public',
      enrollment: 'candidate',
      certified: false,
      event_id: eventId,
      http_status: response.status,
      cf_ray: cfRay,
      latency_ms: latencyMs
    }
  };
  console.log(JSON.stringify(errorResult));
  process.exit(2);
}

const text = body?.choices?.[0]?.message?.content ?? body?.result?.response ?? '';
if (!text || typeof text !== 'string') {
  console.log(JSON.stringify({
    status: 'error',
    text: '',
    metadata: {
      capability: 'hive.ai.general',
      provider: 'cloudflare-workers-ai',
      model,
      transport: 'cloudflare-ai-gateway-rest',
      gateway: 'default',
      route_id: `workers-ai:${model}`,
      source: 'pfarma-ci-public',
      enrollment: 'candidate',
      certified: false,
      event_id: eventId,
      http_status: response.status,
      cf_ray: cfRay,
      latency_ms: latencyMs,
      error: 'empty_model_response'
    }
  }));
  process.exit(3);
}

const modelPath = model.replace(/^@cf\//, '');
const familyParts = modelPath.split('/');
const providerFamily = familyParts.length > 1 ? `${familyParts[0]}/${familyParts[1].split('-').slice(0, 2).join('-')}` : modelPath;

const result = {
  status: 'ok',
  text: text.trim(),
  metadata: {
    capability: 'hive.ai.general',
    provider: 'cloudflare-workers-ai',
    model,
    model_family: providerFamily,
    independence_group: modelPath,
    transport: 'cloudflare-ai-gateway-rest',
    gateway: 'default',
    route_id: `workers-ai:${model}`,
    source: 'pfarma-ci-public',
    enrollment: 'candidate',
    certified: false,
    event_id: eventId,
    http_status: response.status,
    cf_ray: cfRay,
    latency_ms: latencyMs,
    usage: body?.usage || null
  }
};

console.log(JSON.stringify(result));
