#!/usr/bin/env node

function fail(message, code = 1, extra = {}) {
  process.stdout.write(JSON.stringify({
    verified: false,
    score: 0,
    reason: message,
    metadata: { fail_closed: true, ...extra }
  }));
  process.exit(code);
}

function parseJsonEnv(name) {
  const raw = process.env[name];
  if (!raw) fail(`missing_${name.toLowerCase()}`, 10);
  try { return JSON.parse(raw); }
  catch { fail(`invalid_${name.toLowerCase()}`, 11); }
}

function extractJson(text) {
  if (typeof text !== 'string') return null;
  const trimmed = text.trim();
  try { return JSON.parse(trimmed); } catch {}
  const match = trimmed.match(/\{[\s\S]*\}/);
  if (!match) return null;
  try { return JSON.parse(match[0]); } catch { return null; }
}

const worker = parseJsonEnv('HIVE_WORKER_RESULT');
const verifier = parseJsonEnv('HIVE_VERIFIER_RESULT');

if (worker?.status !== 'ok') fail('worker_not_ok', 20);
if (verifier?.status !== 'ok') fail('verifier_not_ok', 21);

const workerGroup = worker?.metadata?.independence_group;
const verifierGroup = verifier?.metadata?.independence_group;
if (!workerGroup || !verifierGroup) fail('missing_independence_group', 22);
if (workerGroup === verifierGroup) {
  fail('verifier_not_independent', 23, { worker_group: workerGroup, verifier_group: verifierGroup });
}

const verdict = extractJson(verifier.text);
if (!verdict || typeof verdict.verified !== 'boolean') fail('invalid_verifier_verdict', 24);

const score = Number(verdict.score);
if (!Number.isFinite(score) || score < 0 || score > 1) fail('invalid_verifier_score', 25);

const output = {
  verified: verdict.verified === true && score >= 0.7,
  score,
  reason: String(verdict.reason || ''),
  metadata: {
    fail_closed: true,
    worker_provider: worker.metadata.provider,
    worker_model: worker.metadata.model,
    worker_model_family: worker.metadata.model_family,
    worker_independence_group: workerGroup,
    verifier_provider: verifier.metadata.provider,
    verifier_model: verifier.metadata.model,
    verifier_model_family: verifier.metadata.model_family,
    verifier_independence_group: verifierGroup,
    transport_independence: worker.metadata.transport !== verifier.metadata.transport,
    model_family_independence: worker.metadata.model_family !== verifier.metadata.model_family
  }
};

process.stdout.write(JSON.stringify(output));
if (!output.verified) process.exit(30);
