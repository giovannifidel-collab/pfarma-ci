import fs from 'node:fs';
import { AGENT_CONFIGS } from './agents.mjs';
import { agentIds, getAgent, closeAll } from './index.mjs';

const expected=['kimi','claude','gemini','deepseek','qwen','mistral','perplexity','copilot','meta','duck'];
const fail=[];
if(AGENT_CONFIGS.length!==10) fail.push(`CONFIG_COUNT=${AGENT_CONFIGS.length}`);
if(agentIds.length!==10) fail.push(`AGENT_ID_COUNT=${agentIds.length}`);
if(new Set(agentIds).size!==10) fail.push('DUPLICATE_IDS');
for(const id of expected) if(!agentIds.includes(id)) fail.push(`MISSING_ID=${id}`);
for(const cfg of AGENT_CONFIGS){
  if(!Number.isInteger(cfg.port)) fail.push(`BAD_PORT=${cfg.id}`);
  if(!(cfg.targetPattern instanceof RegExp)) fail.push(`BAD_TARGET_PATTERN=${cfg.id}`);
  if(!Array.isArray(cfg.composerPatterns)||!cfg.composerPatterns.length) fail.push(`NO_COMPOSER_PATTERNS=${cfg.id}`);
  if(!Array.isArray(cfg.submitPatterns)||!cfg.submitPatterns.length) fail.push(`NO_SUBMIT_PATTERNS=${cfg.id}`);
  if(!cfg.startScript) fail.push(`NO_START_SCRIPT=${cfg.id}`);
  if(!/^https:\/\//.test(String(cfg.homeUrl||''))) fail.push(`NO_HOME_URL=${cfg.id}`);
  const a=getAgent(cfg.id);
  for(const method of ['run','health']) if(typeof a[method]!=='function') fail.push(`MISSING_METHOD=${cfg.id}.${method}`);
}

const registry=JSON.parse(fs.readFileSync(new URL('./registry.json',import.meta.url),'utf8'));
if(registry.certified_count!==10) fail.push(`REGISTRY_CERTIFIED=${registry.certified_count}`);
if(registry.ready_for_hive_count!==10) fail.push(`REGISTRY_READY=${registry.ready_for_hive_count}`);
if(!Array.isArray(registry.agents)||registry.agents.length!==10) fail.push(`REGISTRY_AGENT_COUNT=${registry.agents?.length}`);
for(const id of expected) if(!registry.agents?.some(a=>a.id===id)) fail.push(`REGISTRY_MISSING_ID=${id}`);

const phase=String(registry.phase||'');
const standardized=registry.agents?.filter(a=>a.standardized===true).length||0;
const integrated=registry.agents?.filter(a=>a.hive_integrated===true).length||0;

if(phase==='B_STANDARDIZATION'){
  if(registry.standardized_count!==0) fail.push(`REGISTRY_PREMATURE_STANDARDIZED=${registry.standardized_count}`);
  if(standardized!==0) fail.push(`REGISTRY_PREMATURE_STANDARDIZED_AGENTS=${standardized}`);
  if(registry.hive_integrated_count!==0||integrated!==0) fail.push('REGISTRY_PREMATURE_INTEGRATION');
}else if(phase==='C_STANDARDIZED' || phase==='D_HIVE_INTEGRATION'){
  if(registry.standardized_count!==10||standardized!==10) fail.push(`REGISTRY_STANDARDIZED_MISMATCH=${registry.standardized_count}/${standardized}`);
  if(registry.hive_integrated_count!==0||integrated!==0) fail.push(`REGISTRY_INTEGRATION_MISMATCH=${registry.hive_integrated_count}/${integrated}`);
}else if(phase==='E_HIVE_INTEGRATED'){
  if(registry.standardized_count!==10||standardized!==10) fail.push(`REGISTRY_STANDARDIZED_MISMATCH=${registry.standardized_count}/${standardized}`);
  if(registry.hive_integrated_count!==10||integrated!==10) fail.push(`REGISTRY_INTEGRATED_MISMATCH=${registry.hive_integrated_count}/${integrated}`);
}else{
  fail.push(`REGISTRY_UNKNOWN_PHASE=${phase}`);
}

closeAll();
if(fail.length){console.error('STATIC_VALIDATION=false');for(const x of fail)console.error(`ERROR=${x}`);process.exit(2)}
console.log('STATIC_VALIDATION=true');
console.log('AGENT_COUNT=10');
console.log('CONTRACT=agent.run(task)->{status,text,metadata}');
console.log(`REGISTRY_PHASE=${phase}`);
console.log('RUNTIME_PROOF_REQUIRED=true');
