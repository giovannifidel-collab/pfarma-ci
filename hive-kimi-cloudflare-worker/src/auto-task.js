const AUTO_ID = 'HIVE-KIMI-AUTO-0006';
const AUTO_NONCE = 'HIVE-KIMI-AUTO-OIDC-20260828-V1';
const AUTO_EXPECTED = '139665';
const AUTO_RESULT_KEY = `result:${AUTO_ID}`;
const JINA_READER_PREFIX = 'https://r.jina.ai/';

function json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'access-control-allow-origin': '*',
    },
  });
}

function readerUrl(originUrl) {
  return `${JINA_READER_PREFIX}${originUrl}`;
}

export async function handleAutoTask(request, env) {
  const url = new URL(request.url);
  const parts = url.pathname.split('/').filter(Boolean);

  if (request.method !== 'GET') return json({ ok: false, error: 'method_not_allowed' }, 405);

  if (url.pathname === `/auto/${AUTO_ID}`) {
    const originCallback = `${url.origin}/auto-submit/${AUTO_ID}/${AUTO_NONCE}/<ANSWER>`;
    const resultUrl = `${url.origin}/auto-result/${AUTO_ID}`;
    return json({
      hive: 'HIVE Autonomous Kimi Certification',
      version: '1.0',
      task_id: AUTO_ID,
      test_kind: 'github-actions-autonomous-browser-start',
      purpose: 'Certify that HIVE can start Kimi through the GitHub Actions browser dispatcher without a human opening or prompting Kimi.',
      task: {
        type: 'arithmetic',
        expression: '(8642 * 17) - 12345 + (56 * 91)',
        output: 'Use the resulting integer as <ANSWER> in callback_template.',
      },
      instructions: [
        'Compute the arithmetic expression yourself.',
        'Replace only <ANSWER> in callback_template with the resulting integer.',
        'Open the resulting callback URL exactly once with web_open_url.',
        'Do not remove or modify the r.jina.ai prefix.',
        'Do not ask the user for help or confirmation.',
        'Do not use Python, requests, API keys, Kimi Code, MCP, localhost, or paid tools.',
        'At the end report task_id, computed answer, accepted, certified, duplicate, and the callback response.',
      ],
      callback_template: readerUrl(originCallback),
      result_url: resultUrl,
      reader_result_url: readerUrl(resultUrl),
      security: {
        lab_only: true,
        production_data: false,
        secrets_required_by_kimi: false,
        idempotent: true,
      },
    });
  }

  if (parts[0] === 'auto-submit' && parts.length === 4) {
    const taskId = decodeURIComponent(parts[1]);
    const nonce = decodeURIComponent(parts[2]);
    const answer = decodeURIComponent(parts[3]).trim();

    if (taskId !== AUTO_ID || nonce !== AUTO_NONCE) {
      return json({ ok: false, accepted: false, certified: false, error: 'invalid_auto_task_or_nonce' }, 400);
    }
    if (answer !== AUTO_EXPECTED) {
      return json({ ok: true, accepted: false, certified: false, task_id: AUTO_ID, answer, error: 'wrong_auto_answer' });
    }

    const existing = await env.HIVE_KIMI_RESULTS.get(AUTO_RESULT_KEY, 'json');
    if (existing?.certified === true) {
      return json({
        ok: true,
        accepted: true,
        certified: true,
        duplicate: true,
        task_id: AUTO_ID,
        answer: AUTO_EXPECTED,
        actuator: 'github-actions-playwright',
        bridge: 'jina-reader',
        message: 'HIVE KIMI AUTONOMOUS BROWSER ROUNDTRIP READY',
      });
    }

    const record = {
      certified: true,
      task_id: AUTO_ID,
      answer: AUTO_EXPECTED,
      actuator: 'github-actions-playwright',
      bridge: 'jina-reader',
      received_at: new Date().toISOString(),
      user_agent: request.headers.get('user-agent'),
      cf_ray: request.headers.get('cf-ray'),
    };
    await env.HIVE_KIMI_RESULTS.put(AUTO_RESULT_KEY, JSON.stringify(record));

    return json({
      ok: true,
      accepted: true,
      certified: true,
      duplicate: false,
      task_id: AUTO_ID,
      answer: AUTO_EXPECTED,
      actuator: 'github-actions-playwright',
      bridge: 'jina-reader',
      message: 'HIVE KIMI AUTONOMOUS BROWSER ROUNDTRIP READY',
    });
  }

  if (url.pathname === `/auto-result/${AUTO_ID}`) {
    const record = await env.HIVE_KIMI_RESULTS.get(AUTO_RESULT_KEY, 'json');
    return json({
      ok: true,
      task_id: AUTO_ID,
      certified: record?.certified === true,
      actuator: 'github-actions-playwright',
      bridge: 'jina-reader',
      result: record || null,
    });
  }

  return null;
}
