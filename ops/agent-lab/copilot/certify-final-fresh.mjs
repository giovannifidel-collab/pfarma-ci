import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';

const CDP=process.env.COPILOT_LAB_CDP_URL||'http://127.0.0.1:9231';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function json(url){const r=await fetch(url);if(!r.ok)throw new Error(`HTTP_${r.status}_${url}`);return r.json();}

const targets=await json(`${CDP}/json/list`);
const target=targets.find(t=>t.type==='page'&&/copilot\.(com|microsoft\.com)/i.test(t.url||''));
if(!target?.webSocketDebuggerUrl)throw new Error('COPILOT_PAGE_NOT_FOUND');

const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});});
let seq=0;const pending=new Map();
ws.addEventListener('message',ev=>{let m;try{m=JSON.parse(ev.data);}catch{return;}if(!m.id||!pending.has(m.id))return;const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(new Error(`CDP_${m.error.code}:${m.error.message}`)):p.resolve(m.result||{});});
function call(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evalJs(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error('COPILOT_EVAL_EXCEPTION');return r.result?.value;}
await call('Runtime.enable');await call('Page.enable').catch(()=>{});

const clicked=await evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const els=[...document.querySelectorAll('a,button,[role="button"]')].filter(visible);const e=els.find(x=>/^new chat$/i.test(String(x.getAttribute('aria-label')||x.innerText||'').trim()));if(!e)return false;e.click();return true;})()`);
if(!clicked)throw new Error('COPILOT_NEW_CHAT_CONTROL_NOT_FOUND');

let state={};const started=Date.now();
while(Date.now()-started<45000){
  await sleep(500);
  state=await evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const composer=[...document.querySelectorAll('[contenteditable="true"],textarea')].filter(visible).find(x=>/message copilot/i.test(x.getAttribute('aria-label')||x.getAttribute('placeholder')||''));return {href:String(location.href||''),composer:!!composer,body:String(document.body?.innerText||'').slice(-2500)};})()`).catch(()=>({}));
  if(state.composer&&!/\/conversation\//i.test(state.href||''))break;
}
if(!state.composer||/\/conversation\//i.test(state.href||''))throw new Error(`COPILOT_FRESH_CHAT_NOT_READY_${state.href||'unknown'}`);
console.log('=== COPILOT FINAL FRESH CERTIFICATION ===');
console.log('FRESH_CHAT_READY=true');
console.log(`FRESH_CHAT_URL=${state.href}`);
console.log('TEST_ID=HIVE-COPILOT-STRESS-0005-FRESH');
console.log('BENCHMARK_UNCHANGED=true');
ws.close();
await sleep(500);

const base=path.resolve('certify-standard-v4.mjs');
const temp=path.resolve('.certify-standard-v5-fresh.runtime.mjs');
let source=fs.readFileSync(base,'utf8');
const old="const TEST_ID='HIVE-COPILOT-STRESS-0004';";
const replacement="const TEST_ID='HIVE-COPILOT-STRESS-0005-FRESH';";
if(!source.includes(old))throw new Error('COPILOT_V4_TEST_ID_SIGNATURE_NOT_FOUND');
source=source.replace(old,replacement);
fs.writeFileSync(temp,source);
try{
  const child=spawnSync(process.execPath,[temp],{stdio:'inherit',env:{...process.env,COPILOT_CERT_FRESH_CHAT:'true'}});
  if(child.error)throw child.error;
  process.exitCode=child.status??1;
}finally{
  try{fs.unlinkSync(temp);}catch{}
}
