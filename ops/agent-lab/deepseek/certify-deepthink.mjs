import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const CDP=process.env.DEEPSEEK_LAB_CDP_URL||'http://127.0.0.1:9227';
const OUT_DIR=process.env.DEEPSEEK_LAB_CERT_DIR||path.resolve('certifications');
const TEST_ID='HIVE-DEEPSEEK-STRESS-0001';
const nonce=crypto.randomBytes(4).toString('hex').toUpperCase();
const MASTER={salt:7919,coeff:[17,29,43]};
const SHARDS={A:[311,7,19,23,5],B:[41,53,67,71,73],C:[79,83,89,97,101]};
const SUMS={A:SHARDS.A.reduce((a,b)=>a+b,0),B:SHARDS.B.reduce((a,b)=>a+b,0),C:SHARDS.C.reduce((a,b)=>a+b,0)};
const TERMS={A:MASTER.coeff[0]*SUMS.A,B:MASTER.coeff[1]*SUMS.B,C:MASTER.coeff[2]*SUMS.C};
const EXPECTED=MASTER.salt+TERMS.A+TERMS.B+TERMS.C;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const log=(...x)=>console.log(new Date().toISOString(),...x);

async function json(url,opts={}){
  const r=await fetch(url,opts);
  if(!r.ok) throw new Error(`HTTP_${r.status}_${url}`);
  return r.json();
}

let targets=await json(`${CDP}/json/list`);
let target=targets.find(t=>t.type==='page'&&/chat\.deepseek\.com/i.test(t.url||'')&&!/sign_in/i.test(t.url||''));
if(!target) throw new Error('DEEPSEEK_NOT_AUTHENTICATED_OR_PAGE_NOT_FOUND');
if(!target.webSocketDebuggerUrl) throw new Error('NO_DEEPSEEK_PAGE_WEBSOCKET');

const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);
  ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});
  ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});
});

let seq=0; const pending=new Map();
ws.addEventListener('message',ev=>{
  let msg; try{msg=JSON.parse(ev.data);}catch{return;}
  if(!msg.id||!pending.has(msg.id)) return;
  const p=pending.get(msg.id); pending.delete(msg.id); clearTimeout(p.timer);
  if(msg.error)p.reject(new Error(`CDP_${msg.error.code}:${msg.error.message}`)); else p.resolve(msg.result||{});
});
function call(method,params={}){
  const id=++seq;
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);
    pending.set(id,{resolve,reject,timer});
    ws.send(JSON.stringify({id,method,params}));
  });
}
async function evalJs(expression){
  const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(r.exceptionDetails) throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}_${r.exceptionDetails.exception?.description||''}`);
  return r.result?.value;
}
await call('Runtime.enable');
await call('Page.enable').catch(()=>{});

async function bodyText(){ return evalJs(`String(document.body?.innerText||'')`).catch(()=> ''); }
function literalCount(text,token){ return token ? text.split(token).length-1 : 0; }

async function composerReady(){
  return evalJs(`(()=>{const e=[...document.querySelectorAll('textarea')].find(x=>String(x.getAttribute('placeholder')||'').toLowerCase().includes('message deepseek')&&x.getBoundingClientRect().width>0&&x.getBoundingClientRect().height>0);return !!e})()`);
}

async function modeState(){
  return evalJs(`(()=>{
    const find=name=>[...document.querySelectorAll('[aria-pressed]')].find(e=>String(e.innerText||'').trim()===name&&e.getBoundingClientRect().width>0);
    const d=find('DeepThink'),s=find('Search');
    return {deepthink:d?d.getAttribute('aria-pressed'):null,search:s?s.getAttribute('aria-pressed'):null,deepthinkFound:!!d,searchFound:!!s};
  })()`);
}

async function ensureDeepThink(){
  let s=await modeState();
  if(!s.deepthinkFound||!s.searchFound) throw new Error('DEEPSEEK_MODE_TOGGLES_NOT_FOUND');
  if(s.search==='true'){
    await evalJs(`(()=>{const e=[...document.querySelectorAll('[aria-pressed]')].find(x=>String(x.innerText||'').trim()==='Search'&&x.getBoundingClientRect().width>0);if(!e)return false;e.click();return true})()`);
    await sleep(600);
  }
  s=await modeState();
  if(s.deepthink!=='true'){
    await evalJs(`(()=>{const e=[...document.querySelectorAll('[aria-pressed]')].find(x=>String(x.innerText||'').trim()==='DeepThink'&&x.getBoundingClientRect().width>0);if(!e)return false;e.click();return true})()`);
    await sleep(800);
  }
  s=await modeState();
  if(s.deepthink!=='true'||s.search!=='false') throw new Error(`DEEPSEEK_MODE_VERIFY_FAILED deepthink=${s.deepthink} search=${s.search}`);
  return s;
}

async function send(text){
  await ensureDeepThink();
  const ok=await evalJs(`(()=>{const e=[...document.querySelectorAll('textarea')].find(x=>String(x.getAttribute('placeholder')||'').toLowerCase().includes('message deepseek')&&x.getBoundingClientRect().width>0);if(!e)return false;e.focus();return true})()`);
  if(!ok) throw new Error('DEEPSEEK_COMPOSER_NOT_FOUND');
  await call('Input.dispatchKeyEvent',{type:'rawKeyDown',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
  await call('Input.dispatchKeyEvent',{type:'keyUp',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
  await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
  await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
  await call('Input.insertText',{text});
  await sleep(350);
  const value=await evalJs(`(()=>{const e=[...document.querySelectorAll('textarea')].find(x=>String(x.getAttribute('placeholder')||'').toLowerCase().includes('message deepseek')&&x.getBoundingClientRect().width>0);return e?String(e.value||''):''})()`);
  if(!value||value.length<Math.min(20,text.length)) throw new Error('DEEPSEEK_TEXT_NOT_INSERTED');
  await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
}

async function waitForExact(expected,before,timeout=150000){
  const started=Date.now();
  while(Date.now()-started<timeout){
    const b=await bodyText();
    if(literalCount(b,expected)>=before+2){ await sleep(800); return 'body-occurrence-exact'; }
    await sleep(900);
  }
  throw new Error(`TIMEOUT_WAITING_FOR_EXACT_DEEPSEEK_RESPONSE_${expected}`);
}

async function stage(label,prompt,expectedEcho){
  const before=literalCount(await bodyText(),expectedEcho);
  log('SEND',label);
  await send(prompt);
  const validation=await waitForExact(expectedEcho,before);
  log('PASS',label,validation,'exact-data-echo');
}

function parseFinal(m){
  return {
    salt:Number(m[1]),coeff:[Number(m[2]),Number(m[3]),Number(m[4])],
    sums:{A:Number(m[5]),B:Number(m[6]),C:Number(m[7])},
    terms:{A:Number(m[8]),B:Number(m[9]),C:Number(m[10])},checksum:Number(m[11])
  };
}

async function waitFinal(timeout=210000){
  const started=Date.now();
  const re=new RegExp(`DEEPSEEK_CERT_RESULT:${nonce}:(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+)`,'g');
  while(Date.now()-started<timeout){
    const b=await bodyText();
    const matches=[...b.matchAll(re)];
    if(matches.length) return parseFinal(matches[matches.length-1]);
    await sleep(1000);
  }
  throw new Error(`TIMEOUT_WAITING_FOR_DEEPSEEK_CERT_RESULT_${nonce}`);
}

async function main(){
  fs.mkdirSync(OUT_DIR,{recursive:true});
  const startedAt=new Date().toISOString();
  log(`START ${TEST_ID} nonce=${nonce} expected=${EXPECTED} sums=${SUMS.A},${SUMS.B},${SUMS.C} terms=${TERMS.A},${TERMS.B},${TERMS.C}`);

  const start=Date.now();
  while(Date.now()-start<30000){ if(await composerReady()) break; await sleep(500); }
  if(!await composerReady()) throw new Error('DEEPSEEK_COMPOSER_NOT_READY');
  const mode=await ensureDeepThink();
  log(`MODE DeepThink=${mode.deepthink} Search=${mode.search}`);

  const masterEcho=`ACK_MASTER:${nonce}:${MASTER.salt}:${MASTER.coeff.join(',')}`;
  await stage('MASTER',[
    `${TEST_ID} / ${nonce}`,
    'Memorizza esattamente questo MASTER per un test multi-turn. Non calcolare ancora il risultato finale.',
    `SALT=${MASTER.salt}`,
    `COEFF_A=${MASTER.coeff[0]}`,
    `COEFF_B=${MASTER.coeff[1]}`,
    `COEFF_C=${MASTER.coeff[2]}`,
    `Per confermare i dati ricevuti, rispondi ESATTAMENTE: ${masterEcho}`
  ].join('\n'),masterEcho);

  const echoA=`ACK_A:${nonce}:${SHARDS.A.join(',')}`;
  await stage('SHARD_A',[`${TEST_ID} / ${nonce}`,`SHARD_A=${SHARDS.A.join(',')}`,`Memorizzalo esattamente e rispondi ESATTAMENTE: ${echoA}`].join('\n'),echoA);

  const echoB=`ACK_B:${nonce}:${SHARDS.B.join(',')}`;
  await stage('SHARD_B',[`${TEST_ID} / ${nonce}`,`SHARD_B=${SHARDS.B.join(',')}`,`Memorizzalo esattamente e rispondi ESATTAMENTE: ${echoB}`].join('\n'),echoB);

  const echoC=`ACK_C:${nonce}:${SHARDS.C.join(',')}`;
  await stage('SHARD_C',[`${TEST_ID} / ${nonce}`,`SHARD_C=${SHARDS.C.join(',')}`,`Memorizzalo esattamente e rispondi ESATTAMENTE: ${echoC}`].join('\n'),echoC);

  log('SEND FINAL');
  await send([
    `${TEST_ID} / ${nonce}`,
    'Ora usa SOLO il MASTER e i tre shard memorizzati nei messaggi precedenti.',
    'Recupera SALT e i coefficienti. Calcola SUM_A, SUM_B, SUM_C. Poi TERM_A=COEFF_A*SUM_A, TERM_B=COEFF_B*SUM_B, TERM_C=COEFF_C*SUM_C. Infine CHECKSUM=SALT+TERM_A+TERM_B+TERM_C.',
    'Non aggiungere spiegazioni.',
    `Rispondi ESATTAMENTE nel formato: DEEPSEEK_CERT_RESULT:${nonce}:<SALT>:<COEFF_A>:<COEFF_B>:<COEFF_C>:<SUM_A>:<SUM_B>:<SUM_C>:<TERM_A>:<TERM_B>:<TERM_C>:<CHECKSUM>`
  ].join('\n'));

  const final=await waitFinal();
  const passed=final.salt===MASTER.salt&&final.coeff[0]===MASTER.coeff[0]&&final.coeff[1]===MASTER.coeff[1]&&final.coeff[2]===MASTER.coeff[2]&&final.sums.A===SUMS.A&&final.sums.B===SUMS.B&&final.sums.C===SUMS.C&&final.terms.A===TERMS.A&&final.terms.B===TERMS.B&&final.terms.C===TERMS.C&&final.checksum===EXPECTED;

  const cert={
    test_id:TEST_ID,nonce,provider:'chat.deepseek.com',transport:'persistent-browser-session-direct-cdp',
    mode:{deepthink:true,search:false},api_required:false,zero_cost_api_path:true,
    started_at:startedAt,completed_at:new Date().toISOString(),
    expected:{master:MASTER,sums:SUMS,terms:TERMS,checksum:EXPECTED},actual:final,
    stages:{master:true,shard_a:true,shard_b:true,shard_c:true,final:true},stage_validation:'exact-data-echo',certified:passed
  };
  const file=path.join(OUT_DIR,`${TEST_ID}-${nonce}.json`);
  fs.writeFileSync(file,JSON.stringify(cert,null,2));

  console.log('');
  console.log(`DEEPSEEK_CERTIFIED=${passed?'true':'false'}`);
  console.log(`TEST_ID=${TEST_ID}`);
  console.log(`NONCE=${nonce}`);
  console.log('MODE=DEEPTHINK');
  console.log(`EXPECTED_MASTER=${MASTER.salt}:${MASTER.coeff.join(',')}`);
  console.log(`ACTUAL_MASTER=${final.salt}:${final.coeff.join(',')}`);
  console.log(`EXPECTED_SUMS=${SUMS.A},${SUMS.B},${SUMS.C}`);
  console.log(`ACTUAL_SUMS=${final.sums.A},${final.sums.B},${final.sums.C}`);
  console.log(`EXPECTED_TERMS=${TERMS.A},${TERMS.B},${TERMS.C}`);
  console.log(`ACTUAL_TERMS=${final.terms.A},${final.terms.B},${final.terms.C}`);
  console.log(`EXPECTED_CHECKSUM=${EXPECTED}`);
  console.log(`ACTUAL_CHECKSUM=${final.checksum}`);
  console.log(`CERTIFICATE=${file}`);
  ws.close();
  if(!passed) process.exit(2);
}

main().catch(err=>{
  console.error('DEEPSEEK_CERTIFIED=false');
  console.error(`ERROR=${err.message}`);
  try{ws.close();}catch{}
  process.exit(1);
});
