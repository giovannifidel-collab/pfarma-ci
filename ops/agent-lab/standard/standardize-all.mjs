import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { agentIds, getAgent, closeAll } from './index.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPORTS = path.join(HERE, 'reports');
fs.mkdirSync(REPORTS, { recursive:true });
const sleep = ms => new Promise(r => setTimeout(r, ms));

function argValue(name) {
  const i = process.argv.findIndex(a => a === name || a.startsWith(`${name}=`));
  if (i < 0) return null;
  const a = process.argv[i];
  if (a.includes('=')) return a.slice(a.indexOf('=') + 1);
  return process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : '';
}
const has = name => process.argv.includes(name);
const healthOnly = has('--health');
const retryFailed = has('--retry-failed');
const noFresh = has('--no-fresh');
const onlyRaw = argValue('--only');
const attemptsRaw = Number(argValue('--attempts') || process.env.HIVE_STANDARD_ATTEMPTS || (healthOnly ? 1 : 3));
const maxAttempts = Number.isInteger(attemptsRaw) && attemptsRaw > 0 ? Math.min(attemptsRaw, 5) : 3;
const retryDelayRaw = Number(argValue('--retry-delay-ms') || process.env.HIVE_STANDARD_RETRY_DELAY_MS || 1500);
const retryDelayMs = Number.isFinite(retryDelayRaw) && retryDelayRaw >= 0 ? Math.min(retryDelayRaw, 30000) : 1500;
let selected = onlyRaw ? onlyRaw.split(',').map(x => x.trim().toLowerCase()).filter(Boolean) : [...agentIds];
for (const id of selected) if (!agentIds.includes(id)) throw new Error(`UNKNOWN_AGENT:${id}`);

if (retryFailed) {
  const latest = path.join(REPORTS, 'latest.json');
  if (fs.existsSync(latest)) {
    const prev = JSON.parse(fs.readFileSync(latest, 'utf8'));
    const failed = (prev.results || []).filter(x => !x.pass).map(x => x.id);
    selected = selected.filter(id => failed.includes(id));
    if (!selected.length) {
      console.log('NO_FAILED_AGENTS_TO_RETRY=true');
      process.exit(0);
    }
  }
}

const startedAt = new Date().toISOString();
const results = [];
console.log('=== HIVE ALL-IN-ONE AGENT STANDARDIZATION ===');
console.log('CONTRACT=agent.run(task)->{status,text,metadata}');
console.log(`MODE=${healthOnly?'health':'standardization'}`);
console.log(`AGENTS=${selected.join(',')}`);
console.log(`MAX_ATTEMPTS_PER_AGENT=${maxAttempts}`);
console.log('RECOVERY_POLICY=bounded-self-healing');
console.log('');

function normalizeProbeOutput(v){
  let s=String(v||'').trim();
  s=s.replace(/^<answer>\s*/i,'').replace(/\s*<\/answer>$/i,'').trim();
  s=s.replace(/^['"`]+|['"`]+$/g,'').trim();
  return s;
}

function isHardBlocked(status, text='') {
  if (status !== 'blocked') return false;
  return /(log\s*in|sign\s*in|daily\s*(usage\s*)?limit|rate\s*limit|usage\s*limit|quota|captcha|verification)/i.test(String(text));
}

async function recoverAgent(agent, reason, attempt) {
  if (typeof agent.recover !== 'function') {
    agent.close();
    return { recovered:false, method:'close-only', reason, attempt };
  }
  try {
    return { ...(await agent.recover(reason)), attempt };
  } catch (e) {
    return { recovered:false, method:'recover-exception', reason, error:e.message, attempt };
  }
}

for (const id of selected) {
  const agent = getAgent(id);
  const row = { id, pass:false, attempts:[] };
  const t0 = Date.now();
  console.log(`--- ${id.toUpperCase()} ---`);

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const ar = { attempt, started_at:new Date().toISOString(), pass:false };
    try {
      const health = await agent.health();
      ar.health = health;
      row.health = health;
      console.log(`ATTEMPT=${attempt}/${maxAttempts} HEALTH=${health.status}`);

      if (health.status !== 'ok') {
        ar.error = health.text;
        ar.finished_at = new Date().toISOString();
        row.attempts.push(ar);
        if (isHardBlocked(health.status, health.text) || attempt === maxAttempts) {
          row.error = health.text;
          break;
        }
        const recovery = await recoverAgent(agent, `health:${health.text}`, attempt);
        ar.recovery = recovery;
        console.log(`RECOVERY=${JSON.stringify(recovery)}`);
        await sleep(retryDelayMs * attempt);
        continue;
      }

      if (healthOnly) {
        ar.pass = true;
        ar.finished_at = new Date().toISOString();
        row.attempts.push(ar);
        row.pass = true;
        break;
      }

      const nonce = crypto.randomBytes(4).toString('hex').toUpperCase();
      const expected = `HIVE_STANDARD_OK:${id}:${nonce}`;
      const task = `Standardization probe. Return exactly this token and nothing else: ${expected}`;
      const out = await agent.run(task, { fresh: !noFresh, expectedText: expected });
      const actual = normalizeProbeOutput(out.text);
      const pass = out.status === 'ok' && actual === expected;

      ar.expected = expected;
      ar.raw_actual = String(out.text || '').trim();
      ar.actual = actual;
      ar.output = out;
      ar.pass = pass;
      ar.finished_at = new Date().toISOString();
      row.attempts.push(ar);

      row.output = out;
      row.expected = expected;
      row.raw_actual = ar.raw_actual;
      row.actual = actual;
      row.pass = pass;

      console.log(`ATTEMPT=${attempt}/${maxAttempts} RUN_STATUS=${out.status}`);
      console.log(`EXPECTED=${expected}`);
      console.log(`ACTUAL=${actual}`);
      console.log(`ATTEMPT_PASS=${pass?'true':'false'}`);

      if (pass) break;

      ar.error = out.status === 'ok' ? 'STANDARD_OUTPUT_MISMATCH' : out.text;
      row.error = ar.error;
      const detail = {
        transport: out.metadata?.transport || null,
        fallback_reason: out.metadata?.kimi_cli_fallback_reason || null,
        port: out.metadata?.port || null,
        url: out.metadata?.url || null
      };
      console.log(`DETAIL=${JSON.stringify(detail)}`);

      if (isHardBlocked(out.status, out.text) || attempt === maxAttempts) break;
      const recovery = await recoverAgent(agent, `run:${ar.error}`, attempt);
      ar.recovery = recovery;
      console.log(`RECOVERY=${JSON.stringify(recovery)}`);
      await sleep(retryDelayMs * attempt);
    } catch (e) {
      ar.error = e.message;
      ar.finished_at = new Date().toISOString();
      row.attempts.push(ar);
      row.error = e.message;
      console.log(`ATTEMPT=${attempt}/${maxAttempts} ERROR=${JSON.stringify(e.message)}`);
      if (attempt === maxAttempts) break;
      const recovery = await recoverAgent(agent, `exception:${e.message}`, attempt);
      ar.recovery = recovery;
      console.log(`RECOVERY=${JSON.stringify(recovery)}`);
      await sleep(retryDelayMs * attempt);
    }
  }

  row.attempt_count = row.attempts.length;
  row.recovered = row.pass && row.attempt_count > 1;
  row.latency_ms = Date.now() - t0;
  console.log(`PASS=${row.pass?'true':'false'}`);
  console.log(`ATTEMPTS_USED=${row.attempt_count}`);
  console.log(`RECOVERED=${row.recovered?'true':'false'}`);
  agent.close();
  results.push(row);
  console.log('');
}

closeAll();
const passed = results.filter(x => x.pass).length;
const firstPass = results.filter(x => x.pass && x.attempt_count === 1).length;
const recovered = results.filter(x => x.recovered).length;
const allTenRequested = selected.length === agentIds.length && agentIds.every(id => selected.includes(id));
const ready = !healthOnly && allTenRequested && passed === agentIds.length;
const report = {
  schema_version:'1.1', contract_version:'1.0', phase:'B_STANDARDIZATION_RUNTIME',
  proof_contract:'exact-provider-output-with-bounded-self-healing',
  started_at:startedAt, finished_at:new Date().toISOString(), mode:healthOnly?'health':'standardization',
  requested:selected, retry_budget:maxAttempts, retry_delay_ms:retryDelayMs,
  certified_baseline_count:10, passed_count:passed, first_pass_count:firstPass, recovered_count:recovered,
  failed_count:results.length-passed, standardized_count:ready?10:null,
  ready_for_hive_integration:ready, results
};
const stamp = new Date().toISOString().replace(/[:.]/g,'-');
const file = path.join(REPORTS, `${healthOnly?'health':'standardization'}-${stamp}.json`);
fs.writeFileSync(file, JSON.stringify(report, null, 2));
fs.writeFileSync(path.join(REPORTS, 'latest.json'), JSON.stringify(report, null, 2));

console.log('=== HIVE AGENT STANDARDIZATION REPORT ===');
for (const id of selected) {
  const r = results.find(x => x.id === id);
  const suffix = r?.recovered ? ` (RECOVERED/${r.attempt_count})` : '';
  console.log(`${id.padEnd(12)} ${r?.pass ? 'PASS' : 'FAIL'}${suffix}`);
}
console.log('');
console.log(`PASSED=${passed}/${results.length}`);
console.log(`FIRST_PASS=${firstPass}/${results.length}`);
console.log(`RECOVERED=${recovered}`);
console.log(`FAILED=${results.length-passed}`);
console.log(`STANDARDIZED=${ready?'10/10':'NOT_PROVEN'}`);
console.log(`READY_FOR_HIVE_INTEGRATION=${ready?'true':'false'}`);
console.log(`REPORT=${file}`);
process.exit(results.every(x=>x.pass) ? 0 : 2);
