import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { agentIds } from '../standard/index.mjs';
import { QueenAgentFabric } from './queen-router.mjs';

const HERE=path.dirname(fileURLToPath(import.meta.url));
const REPORTS=path.join(HERE,'reports');
fs.mkdirSync(REPORTS,{recursive:true});

function arg(name){const i=process.argv.findIndex(a=>a===name||a.startsWith(`${name}=`));if(i<0)return null;const a=process.argv[i];if(a.includes('='))return a.slice(a.indexOf('=')+1);return process.argv[i+1]&&!process.argv[i+1].startsWith('--')?process.argv[i+1]:'';}
const attempts=Math.max(1,Math.min(Number(arg('--attempts')||process.env.HIVE_INTEGRATION_ATTEMPTS||3),4));
const semanticAttempts=Math.max(1,Math.min(Number(arg('--semantic-attempts')||2),3));
const startedAt=new Date().toISOString();

function normalize(v){
  let s=String(v||'').trim();
  s=s.replace(/^```(?:text)?\s*/i,'').replace(/\s*```$/,'').trim();
  s=s.replace(/^<answer>\s*/i,'').replace(/\s*<\/answer>$/i,'').trim();
  s=s.replace(/^['"`]+|['"`]+$/g,'').trim();
  return s;
}

async function routingSelfTest(){
  const fake=Object.create(QueenAgentFabric.prototype);
  fake.invoke=async id=>id==='good'?{status:'ok',text:'OK',metadata:{}}:{status:'error',text:`FAIL:${id}`,metadata:{}};
  const fallback=await fake.fallback(['bad','good'],'synthetic');
  const parallel=await fake.parallel(['good','bad'],'synthetic');
  const pass=fallback.status==='ok'&&fallback.metadata?.queen_route==='fallback'&&parallel.status==='partial'&&parallel.metadata?.passed===1&&parallel.metadata?.failed===1;
  return {pass,fallback_status:fallback.status,parallel_status:parallel.status,parallel_metadata:parallel.metadata};
}

const routing=await routingSelfTest();
if(!routing.pass){
  console.error('QUEEN_ROUTING_SELFTEST=false');
  console.error(JSON.stringify(routing));
  process.exit(2);
}
console.log('QUEEN_ROUTING_SELFTEST=true');

const fabric=new QueenAgentFabric({attempts,retryDelayMs:1500,requireIntegrated:false});
const results=[];

for(const id of agentIds){
  console.log(`--- QUEEN -> ${id.toUpperCase()} ---`);
  const row={id,pass:false,semantic_attempts:[]};
  for(let semanticAttempt=1;semanticAttempt<=semanticAttempts;semanticAttempt++){
    const nonce=crypto.randomBytes(4).toString('hex').toUpperCase();
    const expected=`HIVE_QUEEN_OK:${id}:${nonce}`;
    const task=`Queen integration probe. Return exactly this token and nothing else: ${expected}`;
    const out=await fabric.invoke(id,task,{attempts,fresh:true});
    const actual=normalize(out.text);
    const pass=out.status==='ok'&&actual===expected;
    row.semantic_attempts.push({attempt:semanticAttempt,expected,actual,status:out.status,pass,metadata:out.metadata});
    row.expected=expected;
    row.actual=actual;
    row.output=out;
    row.pass=pass;
    console.log(`SEMANTIC_ATTEMPT=${semanticAttempt}/${semanticAttempts}`);
    console.log(`RUN_STATUS=${out.status}`);
    console.log(`EXPECTED=${expected}`);
    console.log(`ACTUAL=${actual}`);
    console.log(`PASS=${pass?'true':'false'}`);
    if(pass)break;
  }
  results.push(row);
  console.log('');
}

fabric.close();
const passed=results.filter(r=>r.pass).length;
const ready=routing.pass&&passed===agentIds.length;
const report={
  schema_version:'1.0',
  phase:'QUEEN_HIVE_INTEGRATION',
  contract:'QueenAgentFabric -> standard agent.run(task) -> exact provider output',
  started_at:startedAt,
  finished_at:new Date().toISOString(),
  requested:[...agentIds],
  routing_selftest:routing,
  invoke_attempt_budget:attempts,
  semantic_attempt_budget:semanticAttempts,
  passed_count:passed,
  failed_count:results.length-passed,
  ready,
  results
};
const stamp=new Date().toISOString().replace(/[:.]/g,'-');
const file=path.join(REPORTS,`queen-integration-${stamp}.json`);
fs.writeFileSync(file,JSON.stringify(report,null,2));
fs.writeFileSync(path.join(REPORTS,'latest.json'),JSON.stringify(report,null,2));

console.log('=== QUEEN / HIVE INTEGRATION REPORT ===');
for(const id of agentIds){const r=results.find(x=>x.id===id);console.log(`${id.padEnd(12)} ${r?.pass?'PASS':'FAIL'}`);}
console.log('');
console.log(`PASSED=${passed}/${results.length}`);
console.log(`FAILED=${results.length-passed}`);
console.log(`QUEEN_ROUTING_SELFTEST=${routing.pass?'true':'false'}`);
console.log(`HIVE_INTEGRATION_READY=${ready?'true':'false'}`);
console.log(`REPORT=${file}`);
process.exit(ready?0:2);
