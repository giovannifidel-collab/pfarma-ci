import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { agentIds, getAgent, closeAll } from './index.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPORTS = path.join(HERE, 'reports');
fs.mkdirSync(REPORTS, { recursive:true });

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
console.log(`CONTRACT=agent.run(task)->{status,text,metadata}`);
console.log(`MODE=${healthOnly?'health':'standardization'}`);
console.log(`AGENTS=${selected.join(',')}`);
console.log('');

for (const id of selected) {
  const agent = getAgent(id);
  const row = { id, pass:false };
  const t0 = Date.now();
  console.log(`--- ${id.toUpperCase()} ---`);
  try {
    const health = await agent.health();
    row.health = health;
    console.log(`HEALTH=${health.status}`);
    if (health.status !== 'ok') {
      row.error = health.text;
      console.log(`PASS=false ERROR=${JSON.stringify(health.text)}`);
      results.push(row); agent.close(); continue;
    }
    if (healthOnly) {
      row.pass = true;
      row.latency_ms = Date.now() - t0;
      console.log('PASS=true');
      results.push(row); agent.close(); continue;
    }

    const nonce = crypto.randomBytes(4).toString('hex').toUpperCase();
    const expected = `HIVE_STANDARD_OK:${id}:${nonce}`;
    const task = `Standardization probe. Return exactly this token and nothing else: ${expected}`;
    const out = await agent.run(task, { fresh: !noFresh });
    row.output = out;
    row.expected = expected;
    row.actual = String(out.text || '').trim();
    row.pass = out.status === 'ok' && row.actual === expected;
    row.latency_ms = Date.now() - t0;
    console.log(`RUN_STATUS=${out.status}`);
    console.log(`EXPECTED=${expected}`);
    console.log(`ACTUAL=${row.actual}`);
    console.log(`PASS=${row.pass?'true':'false'}`);
    if (!row.pass) row.error = out.status === 'ok' ? 'STANDARD_OUTPUT_MISMATCH' : out.text;
  } catch (e) {
    row.error = e.message;
    row.latency_ms = Date.now() - t0;
    console.log(`PASS=false ERROR=${JSON.stringify(e.message)}`);
  } finally {
    agent.close();
    results.push(...(results.includes(row) ? [] : [row]));
    console.log('');
  }
}

closeAll();
const passed = results.filter(x => x.pass).length;
const allTenRequested = selected.length === agentIds.length && agentIds.every(id => selected.includes(id));
const ready = !healthOnly && allTenRequested && passed === agentIds.length;
const report = {
  schema_version:'1.0', contract_version:'1.0', phase:'B_STANDARDIZATION_RUNTIME',
  started_at:startedAt, finished_at:new Date().toISOString(), mode:healthOnly?'health':'standardization',
  requested:selected, certified_baseline_count:10, passed_count:passed, failed_count:results.length-passed,
  standardized_count:ready?10:null, ready_for_hive_integration:ready, results
};
const stamp = new Date().toISOString().replace(/[:.]/g,'-');
const file = path.join(REPORTS, `${healthOnly?'health':'standardization'}-${stamp}.json`);
fs.writeFileSync(file, JSON.stringify(report, null, 2));
fs.writeFileSync(path.join(REPORTS, 'latest.json'), JSON.stringify(report, null, 2));

console.log('=== HIVE AGENT STANDARDIZATION REPORT ===');
for (const id of selected) {
  const r = results.find(x => x.id === id);
  console.log(`${id.padEnd(12)} ${r?.pass ? 'PASS' : 'FAIL'}`);
}
console.log('');
console.log(`PASSED=${passed}/${results.length}`);
console.log(`FAILED=${results.length-passed}`);
console.log(`STANDARDIZED=${ready?'10/10':'NOT_PROVEN'}`);
console.log(`READY_FOR_HIVE_INTEGRATION=${ready?'true':'false'}`);
console.log(`REPORT=${file}`);
process.exit(results.every(x=>x.pass) ? 0 : 2);
