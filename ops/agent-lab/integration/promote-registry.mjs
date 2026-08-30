import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { agentIds } from '../standard/index.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REGISTRY_PATH = path.resolve(HERE, '../standard/registry.json');
const PROOF_LOCK_PATH = path.resolve(HERE, '../standard/proof-lock.json');

function arg(name) {
  const i=process.argv.findIndex(a=>a===name||a.startsWith(`${name}=`));
  if(i<0)return null;
  const a=process.argv[i];
  if(a.includes('='))return a.slice(a.indexOf('=')+1);
  return process.argv[i+1]&&!process.argv[i+1].startsWith('--')?process.argv[i+1]:'';
}

function sha256File(file){return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');}
function readJson(file){return JSON.parse(fs.readFileSync(file,'utf8'));}
function writeJson(file,obj){fs.writeFileSync(file,JSON.stringify(obj,null,2)+'\n');}
function exactIds(list){return Array.isArray(list)&&list.length===agentIds.length&&agentIds.every(id=>list.includes(id));}

const stage=String(arg('--stage')||'').toLowerCase();
if(!['standardized','begin-integration','integrated'].includes(stage)){
  console.error('Usage: node promote-registry.mjs --stage standardized|begin-integration|integrated [--report path]');
  process.exit(64);
}

const registry=readJson(REGISTRY_PATH);
const stamp=new Date().toISOString();

if(stage==='standardized'){
  const reportPath=path.resolve(arg('--report')||path.resolve(HERE,'../standard/reports/latest.json'));
  if(!fs.existsSync(reportPath))throw new Error(`STANDARDIZATION_REPORT_NOT_FOUND:${reportPath}`);
  const report=readJson(reportPath);
  const valid = report.mode==='standardization' && exactIds(report.requested) && report.passed_count===10 && report.failed_count===0 && report.standardized_count===10 && report.ready_for_hive_integration===true && Array.isArray(report.results) && agentIds.every(id=>report.results.some(r=>r.id===id&&r.pass===true));
  if(!valid)throw new Error('STANDARDIZATION_PROOF_GATE_FAILED');

  registry.phase='C_STANDARDIZED';
  registry.standardized_count=10;
  registry.hive_integrated_count=0;
  registry.standardization_proof={
    report:path.basename(reportPath),
    sha256:sha256File(reportPath),
    proof_contract:report.proof_contract||'exact-provider-output',
    passed_count:report.passed_count,
    recovered_count:report.recovered_count||0,
    finished_at:report.finished_at,
    promoted_at:stamp
  };
  registry.agents=registry.agents.map(a=>({...a,standardized:true,hive_integrated:false}));
  writeJson(REGISTRY_PATH,registry);
  writeJson(PROOF_LOCK_PATH,{
    schema_version:'1.0',
    standardization:{...registry.standardization_proof,agent_ids:[...agentIds]},
    integration:null
  });
  console.log('REGISTRY_PROMOTED=C_STANDARDIZED');
  console.log('STANDARDIZED=10/10');
  process.exit(0);
}

if(stage==='begin-integration'){
  if(registry.standardized_count!==10||registry.agents?.filter(a=>a.standardized===true).length!==10)throw new Error('STANDARDIZED_REGISTRY_REQUIRED');
  if(!registry.standardization_proof?.sha256)throw new Error('STANDARDIZATION_PROOF_LOCK_REQUIRED');
  registry.phase='D_HIVE_INTEGRATION';
  registry.hive_integrated_count=0;
  registry.integration_started_at=stamp;
  registry.agents=registry.agents.map(a=>({...a,hive_integrated:false}));
  writeJson(REGISTRY_PATH,registry);
  console.log('REGISTRY_PROMOTED=D_HIVE_INTEGRATION');
  process.exit(0);
}

const reportPath=path.resolve(arg('--report')||path.resolve(HERE,'reports/latest.json'));
if(!fs.existsSync(reportPath))throw new Error(`INTEGRATION_REPORT_NOT_FOUND:${reportPath}`);
const report=readJson(reportPath);
const valid = registry.phase==='D_HIVE_INTEGRATION' && registry.standardized_count===10 && report.phase==='QUEEN_HIVE_INTEGRATION' && report.passed_count===10 && report.failed_count===0 && report.ready===true && exactIds(report.requested) && Array.isArray(report.results) && agentIds.every(id=>report.results.some(r=>r.id===id&&r.pass===true));
if(!valid)throw new Error('INTEGRATION_PROOF_GATE_FAILED');

registry.phase='E_HIVE_INTEGRATED';
registry.hive_integrated_count=10;
registry.integration_proof={
  report:path.basename(reportPath),
  sha256:sha256File(reportPath),
  passed_count:10,
  finished_at:report.finished_at,
  promoted_at:stamp
};
registry.agents=registry.agents.map(a=>({...a,standardized:true,hive_integrated:true}));
writeJson(REGISTRY_PATH,registry);

const lock=fs.existsSync(PROOF_LOCK_PATH)?readJson(PROOF_LOCK_PATH):{schema_version:'1.0',standardization:null};
lock.integration={...registry.integration_proof,agent_ids:[...agentIds]};
writeJson(PROOF_LOCK_PATH,lock);
console.log('REGISTRY_PROMOTED=E_HIVE_INTEGRATED');
console.log('HIVE_INTEGRATED=10/10');
