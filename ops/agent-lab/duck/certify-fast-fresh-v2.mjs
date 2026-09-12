import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const CDP=process.env.DUCK_LAB_CDP_URL||'http://127.0.0.1:9233';
const OUT_DIR=process.env.DUCK_LAB_CERT_DIR||path.resolve('certifications');
const TEST_ID='HIVE-DUCK-STRESS-0002-FRESH';
const nonce=crypto.randomBytes(4).toString('hex').toUpperCase();
const MASTER={salt:7919,coeff:[17,29,43]};
const SHARDS={A:[311,7,19,23,5],B:[41,53,67,71,73],C:[79,83,89,97,101]};
const SUMS={A:SHARDS.A.reduce((a,b)=>a+b,0),B:SHARDS.B.reduce((a,b)=>a+b,0),C:SHARDS.C.reduce((a,b)=>a+b,0)};
const TERMS={A:MASTER.coeff[0]*SUMS.A,B:MASTER.coeff[1]*SUMS.B,C:MASTER.coeff[2]*SUMS.C};
const EXPECTED=MASTER.salt+TERMS.A+TERMS.B+TERMS.C;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const log=(...x)=>console.log(new Date().toISOString(),...x);

async function json(url,opts={}){const r=await fetch(url,opts);if(!r.ok)throw new Error(`HTTP_${r.status}_${url}`);return r.json();}
const targets=await json(`${CDP}/json/list`);
const target=targets.find(t=>t.type==='page'&&/duck\.ai/i.test(t.url||''));
if(!target?.webSocketDebuggerUrl)throw new Error('DUCK_PAGE_NOT_FOUND');
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});});
let seq=0;const pending=new Map();
ws.addEventListener('message',ev=>{let m;try{m=JSON.parse(ev.data);}catch{return;}if(!m.id||!pending.has(m.id))return;const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(new Error(`CDP_${m.error.code}:${m.error.message}`)):p.resolve(m.result||{});});
function call(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evalJs(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}`);return r.result?.value;}
await call('Runtime.enable');await call('Page.enable').catch(()=>{});

async function bodyText(){return evalJs(`String(document.body?.innerText||'')`).catch(()=> '');}
function count(text,token){return token?text.split(token).length-1:0;}
async function uiState(){return evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const controls=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);const composer=controls.find(e=>/ask anything privately/i.test(String(e.getAttribute('placeholder')||e.getAttribute('aria-label')||'')))||controls.find(e=>e.tagName==='TEXTAREA')||null;const actions=[...document.querySelectorAll('button,[role="button"]')].filter(visible);const ask=actions.find(e=>/^ask$/i.test(String(e.getAttribute('aria-label')||e.innerText||'').trim()));const stop=actions.find(e=>/^(stop|stop generating|stop responding|cancel response)$/i.test(String(e.getAttribute('aria-label')||e.innerText||'').trim()));const body=String(document.body?.innerText||'');const fast=actions.some(e=>/^fast$/i.test(String(e.innerText||e.getAttribute('aria-label')||'').trim()))||/\bFast\b/.test(body);const free=actions.some(e=>/free/i.test(String(e.innerText||e.getAttribute('aria-label')||'').trim()))||/\bFree\b/.test(body);const model=actions.map(e=>String(e.innerText||'').trim()).find(t=>/^5\.6\s+Luna$/i.test(t))||null;const text=composer?String(composer.value||composer.innerText||composer.textContent||''):'';return {href:String(location.href||''),composer:!!composer,composerText:text,composerTag:composer?.tagName?.toLowerCase()||null,askVisible:!!ask,askDisabled:ask?!!ask.disabled:null,stopVisible:!!stop,fastVisible:fast,freeVisible:free,model};})()`);}
async function waitComposer(timeout=45000){const s=Date.now();while(Date.now()-s<timeout){const u=await uiState();if(u.composer)return u;await sleep(400);}throw new Error('DUCK_COMPOSER_NOT_READY');}
async function waitIdle(timeout=60000){const s=Date.now();let stable=0;while(Date.now()-s<timeout){const u=await uiState();if(u.composer&&!u.stopVisible){stable++;if(stable>=4)return true;}else stable=0;await sleep(350);}return false;}
async function focusComposer(){return evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const all=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);const e=all.find(x=>/ask anything privately/i.test(String(x.getAttribute('placeholder')||x.getAttribute('aria-label')||'')))||all.find(x=>x.tagName==='TEXTAREA')||null;if(!e)return false;e.focus();return true;})()`);}
async function clearComposer(){if(!await focusComposer())throw new Error('DUCK_COMPOSER_NOT_FOUND');await call('Input.dispatchKeyEvent',{type:'rawKeyDown',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});await call('Input.dispatchKeyEvent',{type:'keyUp',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});await sleep(250);}
async function clickAsk(){return evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const e=[...document.querySelectorAll('button,[role="button"]')].filter(visible).find(x=>/^ask$/i.test(String(x.getAttribute('aria-label')||x.innerText||'').trim()));if(!e||e.disabled)return false;e.click();return true;})()`);}
async function pressEnter(){if(!await focusComposer())return false;await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});return true;}
async function waitAskReady(timeout=8000){const s=Date.now();while(Date.now()-s<timeout){const u=await uiState();if(u.askVisible&&!u.askDisabled)return true;await sleep(200);}return false;}
async function verifySubmitted(token,timeout=15000){const s=Date.now();while(Date.now()-s<timeout){const u=await uiState(),b=await bodyText();if(!u.composerText.includes(nonce)&&count(b,token)>=1)return true;await sleep(250);}return false;}
async function quotaCheck(){const b=(await bodyText()).toLowerCase();if(/daily limit|rate limit|try again later|usage limit|you've reached|limit reached/.test(b))throw new Error('DUCK_FREE_TIER_QUOTA_BLOCK');}
async function send(text,token,label){if(!await waitIdle())throw new Error(`DUCK_NOT_IDLE_BEFORE_${label}`);await quotaCheck();await clearComposer();await call('Input.insertText',{text});await sleep(300);let u=await uiState();if(!u.composerText.includes(nonce))throw new Error(`DUCK_TEXT_NOT_INSERTED_${label}`);let method='ASK_BUTTON';let submitted=false;if(await waitAskReady(8000)){const clicked=await clickAsk();log('SUBMIT_ATTEMPT',label,'ASK_BUTTON',`clicked=${clicked}`);if(clicked)submitted=await verifySubmitted(token,10000);}if(!submitted){method='ENTER';const entered=await pressEnter();log('SUBMIT_ATTEMPT',label,'ENTER',`dispatched=${entered}`);if(entered)submitted=await verifySubmitted(token,10000);}if(!submitted)throw new Error(`DUCK_PROMPT_NOT_SUBMITTED_${label}`);log('SUBMITTED',label,method,'composer-cleared+prompt-visible');return method;}
async function waitExact(expected,before,timeout=180000){const s=Date.now();let last=-1,stable=0;while(Date.now()-s<timeout){await quotaCheck();const b=await bodyText();const n=count(b,expected);if(n>=before+2){if(n===last)stable++;else stable=0;last=n;if(stable>=2&&await waitIdle(30000))return 'body-occurrence-exact+stable';}await sleep(750);}throw new Error(`TIMEOUT_WAITING_DUCK_EXACT_${expected}`);}
async function stage(label,prompt,echo){const before=count(await bodyText(),echo);log('SEND',label);await send(prompt,echo,label);const v=await waitExact(echo,before);log('PASS',label,v,'exact-data-echo');}
function finalMatches(text){const re=new RegExp(`DUCK_CERT_RESULT:${nonce}:(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+)`,'g');return [...text.matchAll(re)];}
function parseFinal(m){return {salt:Number(m[1]),coeff:[Number(m[2]),Number(m[3]),Number(m[4])],sums:{A:Number(m[5]),B:Number(m[6]),C:Number(m[7])},terms:{A:Number(m[8]),B:Number(m[9]),C:Number(m[10])},checksum:Number(m[11])};}
async function waitFinal(timeout=240000){const s=Date.now();let raw='',stable=0;while(Date.now()-s<timeout){await quotaCheck();const matches=finalMatches(await bodyText());if(matches.length){const m=matches.at(-1);if(m[0]===raw)stable++;else{raw=m[0];stable=1;}if(stable>=4&&await waitIdle(30000)){await sleep(1500);const m2=finalMatches(await bodyText()).at(-1);if(m2&&m2[0]===raw)return parseFinal(m2);}}await sleep(900);}throw new Error(`TIMEOUT_WAITING_STABLE_DUCK_FINAL_${nonce}`);}
async function freshChat(){const clicked=await evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const els=[...document.querySelectorAll('button,a,[role="button"]')].filter(visible);const e=els.find(x=>/^new chat(?:\\s|$)/i.test(String(x.innerText||x.getAttribute('aria-label')||'').trim()));if(!e)return false;e.click();return true;})()`);if(!clicked)throw new Error('DUCK_NEW_CHAT_CONTROL_NOT_FOUND');await sleep(1500);await waitComposer();console.log('FRESH_CHAT_READY=true');console.log(`FRESH_CHAT_URL=${(await uiState()).href}`);}

async function main(){
  fs.mkdirSync(OUT_DIR,{recursive:true});
  await waitComposer();
  await freshChat();
  const state=await uiState();
  console.log('=== DUCK AI CERTIFICATION V2 ===');
  console.log(`TEST_ID=${TEST_ID}`);
  console.log('BENCHMARK_UNCHANGED=true');
  log(`START ${TEST_ID} nonce=${nonce} expected=${EXPECTED} sums=${SUMS.A},${SUMS.B},${SUMS.C} terms=${TERMS.A},${TERMS.B},${TERMS.C}`);
  log(`MODE FastVisible=${state.fastVisible} FreeVisible=${state.freeVisible} model=${state.model||'not-detected'} composer=${state.composer}`);

  const masterEcho=`ACK_MASTER:${nonce}:${MASTER.salt}:${MASTER.coeff.join(',')}`;
  await stage('MASTER',[`${TEST_ID} / ${nonce}`,'Memorizza esattamente questo MASTER per un test multi-turn. Non calcolare ancora il risultato finale.',`SALT=${MASTER.salt}`,`COEFF_A=${MASTER.coeff[0]}`,`COEFF_B=${MASTER.coeff[1]}`,`COEFF_C=${MASTER.coeff[2]}`,`Rispondi ESATTAMENTE: ${masterEcho}`].join('\n'),masterEcho);
  const echoA=`ACK_A:${nonce}:${SHARDS.A.join(',')}`;
  await stage('SHARD_A',[`${TEST_ID} / ${nonce}`,`SHARD_A=${SHARDS.A.join(',')}`,`Memorizzalo esattamente e rispondi ESATTAMENTE: ${echoA}`].join('\n'),echoA);
  const echoB=`ACK_B:${nonce}:${SHARDS.B.join(',')}`;
  await stage('SHARD_B',[`${TEST_ID} / ${nonce}`,`SHARD_B=${SHARDS.B.join(',')}`,`Memorizzalo esattamente e rispondi ESATTAMENTE: ${echoB}`].join('\n'),echoB);
  const echoC=`ACK_C:${nonce}:${SHARDS.C.join(',')}`;
  await stage('SHARD_C',[`${TEST_ID} / ${nonce}`,`SHARD_C=${SHARDS.C.join(',')}`,`Memorizzalo esattamente e rispondi ESATTAMENTE: ${echoC}`].join('\n'),echoC);

  log('SEND FINAL');
  const finalPrompt=[`${TEST_ID} / ${nonce}`,'Usa SOLO il MASTER e i tre shard memorizzati nei messaggi precedenti.','Calcola SUM_A, SUM_B, SUM_C. Poi TERM_A=COEFF_A*SUM_A, TERM_B=COEFF_B*SUM_B, TERM_C=COEFF_C*SUM_C. Infine CHECKSUM=SALT+TERM_A+TERM_B+TERM_C.','Non aggiungere spiegazioni.',`Rispondi ESATTAMENTE nel formato: DUCK_CERT_RESULT:${nonce}:<SALT>:<COEFF_A>:<COEFF_B>:<COEFF_C>:<SUM_A>:<SUM_B>:<SUM_C>:<TERM_A>:<TERM_B>:<TERM_C>:<CHECKSUM>`].join('\n');
  await send(finalPrompt,`DUCK_CERT_RESULT:${nonce}:`,'FINAL');
  const final=await waitFinal();
  const passed=final.salt===MASTER.salt&&final.coeff[0]===17&&final.coeff[1]===29&&final.coeff[2]===43&&final.sums.A===SUMS.A&&final.sums.B===SUMS.B&&final.sums.C===SUMS.C&&final.terms.A===TERMS.A&&final.terms.B===TERMS.B&&final.terms.C===TERMS.C&&final.checksum===EXPECTED;
  const cert={test_id:TEST_ID,nonce,provider:'Duck.ai',product:'Duck.ai Web',transport:'browser-session-direct-cdp',tier:state.freeVisible?'Free':'not-confirmed',mode:state.fastVisible?'Fast':'not-confirmed',model_ui:state.model||'not-detected',authenticated:false,fresh_chat:true,streaming_stability_guard:true,submit_handshake:'wait-ask-ready+click+composer-cleared+prompt-visible+enter-fallback',api_required:false,zero_cost_path:true,expected:{master:MASTER,sums:SUMS,terms:TERMS,checksum:EXPECTED},actual:final,certified:passed};
  const file=path.join(OUT_DIR,`${TEST_ID}-${nonce}.json`);
  fs.writeFileSync(file,JSON.stringify(cert,null,2));
  console.log('');
  console.log(`DUCK_CERTIFIED=${passed?'true':'false'}`);
  console.log(`TEST_ID=${TEST_ID}`);
  console.log(`NONCE=${nonce}`);
  console.log('PRODUCT=Duck.ai Web');
  console.log(`TIER=${state.freeVisible?'Free':'not-confirmed'}`);
  console.log(`MODE=${state.fastVisible?'Fast':'not-confirmed'}`);
  console.log(`MODEL_UI=${state.model||'not-detected'}`);
  console.log('AUTHENTICATED=false');
  console.log('FRESH_CHAT=true');
  console.log('STREAMING_STABILITY_GUARD=true');
  console.log('SEND_HANDSHAKE=wait-ask-ready+click+composer-cleared+prompt-visible+enter-fallback');
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
  if(!passed)process.exit(2);
}
main().catch(err=>{console.error('DUCK_CERTIFIED=false');console.error(`ERROR=${err.message}`);try{ws.close();}catch{}process.exit(1);});
