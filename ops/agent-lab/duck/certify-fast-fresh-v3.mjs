import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const CDP=process.env.DUCK_LAB_CDP_URL||'http://127.0.0.1:9233';
const OUT_DIR=process.env.DUCK_LAB_CERT_DIR||path.resolve('certifications');
const TEST_ID='HIVE-DUCK-STRESS-0003-FRESH';
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
async function uiState(){return evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const controls=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);const composer=controls.find(e=>/ask anything privately/i.test(String(e.getAttribute('placeholder')||e.getAttribute('aria-label')||'')))||controls.find(e=>e.tagName==='TEXTAREA')||null;const actions=[...document.querySelectorAll('button,[role="button"],input[type="submit"]')].filter(visible);const send=actions.find(e=>/^send$/i.test(String(e.getAttribute('aria-label')||e.innerText||e.value||'').trim()))||actions.find(e=>e.tagName==='BUTTON'&&String(e.getAttribute('type')||'').toLowerCase()==='submit');const stop=actions.find(e=>/^(stop|stop generating|stop responding|cancel response)$/i.test(String(e.getAttribute('aria-label')||e.innerText||'').trim()));const body=String(document.body?.innerText||'');const fast=actions.some(e=>/^fast$/i.test(String(e.innerText||e.getAttribute('aria-label')||'').trim()))||/\bFast\b/.test(body);const free=actions.some(e=>/free/i.test(String(e.innerText||e.getAttribute('aria-label')||'').trim()))||/\bFree\b/.test(body);const model=actions.map(e=>String(e.innerText||'').trim()).find(t=>/^5\.6\s+Luna$/i.test(t))||null;const text=composer?String(composer.value||composer.innerText||composer.textContent||''):'';return {href:String(location.href||''),composer:!!composer,composerText:text,composerTag:composer?.tagName?.toLowerCase()||null,sendVisible:!!send,sendDisabled:send?!!send.disabled:null,sendAria:send?.getAttribute('aria-label')||null,sendType:send?.getAttribute('type')||null,stopVisible:!!stop,fastVisible:fast,freeVisible:free,model};})()`);}
async function waitComposer(timeout=45000){const s=Date.now();while(Date.now()-s<timeout){const u=await uiState();if(u.composer)return u;await sleep(400);}throw new Error('DUCK_COMPOSER_NOT_READY');}
async function waitIdle(timeout=60000){const s=Date.now();let stable=0;while(Date.now()-s<timeout){const u=await uiState();if(u.composer&&!u.stopVisible){stable++;if(stable>=4)return true;}else stable=0;await sleep(350);}return false;}
async function quotaCheck(){const b=(await bodyText()).toLowerCase();if(/daily limit|rate limit|try again later|usage limit|you've reached|limit reached/.test(b))throw new Error('DUCK_FREE_TIER_QUOTA_BLOCK');}
async function setComposerValue(text){const payload=JSON.stringify(text);return evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const all=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);const e=all.find(x=>/ask anything privately/i.test(String(x.getAttribute('placeholder')||x.getAttribute('aria-label')||'')))||all.find(x=>x.tagName==='TEXTAREA')||null;if(!e)return {ok:false,error:'NO_COMPOSER'};e.focus();const value=${payload};if(e instanceof HTMLTextAreaElement){const d=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value');d?.set?d.set.call(e,value):e.value=value;}else if(e instanceof HTMLInputElement){const d=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');d?.set?d.set.call(e,value):e.value=value;}else{e.textContent=value;}try{e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:value}));}catch{e.dispatchEvent(new Event('input',{bubbles:true}));}e.dispatchEvent(new Event('change',{bubbles:true}));return {ok:true,value:String(e.value||e.innerText||e.textContent||'')};})()`);}
async function waitSendReady(timeout=10000){const s=Date.now();while(Date.now()-s<timeout){const u=await uiState();if(u.sendVisible&&!u.sendDisabled)return u;await sleep(200);}return null;}
async function clickSend(){return evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const actions=[...document.querySelectorAll('button,[role="button"],input[type="submit"]')].filter(visible);const e=actions.find(x=>/^send$/i.test(String(x.getAttribute('aria-label')||x.innerText||x.value||'').trim()))||actions.find(x=>x.tagName==='BUTTON'&&String(x.getAttribute('type')||'').toLowerCase()==='submit');if(!e||e.disabled)return false;e.click();return true;})()`);}
async function verifySubmitted(token,timeout=15000){const s=Date.now();while(Date.now()-s<timeout){const u=await uiState(),b=await bodyText();if(!u.composerText.includes(nonce)&&count(b,token)>=1)return true;await sleep(250);}return false;}
async function send(text,token,label){if(!await waitIdle())throw new Error(`DUCK_NOT_IDLE_BEFORE_${label}`);await quotaCheck();const set=await setComposerValue(text);if(!set?.ok||!String(set.value||'').includes(nonce))throw new Error(`DUCK_TEXT_NOT_INSERTED_${label}`);const ready=await waitSendReady(10000);if(!ready)throw new Error(`DUCK_SEND_NOT_READY_${label}`);log('SEND_READY',label,`aria=${ready.sendAria||'null'}`,`type=${ready.sendType||'null'}`);const clicked=await clickSend();log('SUBMIT_ATTEMPT',label,'SEND_BUTTON',`clicked=${clicked}`);if(!clicked)throw new Error(`DUCK_SEND_CLICK_FAILED_${label}`);if(!await verifySubmitted(token))throw new Error(`DUCK_PROMPT_NOT_SUBMITTED_${label}`);log('SUBMITTED',label,'SEND_BUTTON','composer-cleared+prompt-visible');return 'SEND_BUTTON';}
async function waitExact(expected,before,timeout=180000){const s=Date.now();let last=-1,stable=0;while(Date.now()-s<timeout){await quotaCheck();const b=await bodyText();const n=count(b,expected);if(n>=before+2){if(n===last)stable++;else stable=0;last=n;if(stable>=2&&await waitIdle(30000))return 'body-occurrence-exact+stable';}await sleep(750);}throw new Error(`TIMEOUT_WAITING_DUCK_EXACT_${expected}`);}
async function stage(label,prompt,echo){const before=count(await bodyText(),echo);log('SEND',label);await send(prompt,echo,label);const v=await waitExact(echo,before);log('PASS',label,v,'exact-data-echo');}
function finalMatches(text){const re=new RegExp(`DUCK_CERT_RESULT:${nonce}:(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+)`,'g');return [...text.matchAll(re)];}
function parseFinal(m){return {salt:Number(m[1]),coeff:[Number(m[2]),Number(m[3]),Number(m[4])],sums:{A:Number(m[5]),B:Number(m[6]),C:Number(m[7])},terms:{A:Number(m[8]),B:Number(m[9]),C:Number(m[10])},checksum:Number(m[11])};}
async function waitFinal(timeout=240000){const s=Date.now();let raw='',stable=0;while(Date.now()-s<timeout){await quotaCheck();const matches=finalMatches(await bodyText());if(matches.length){const m=matches.at(-1);if(m[0]===raw)stable++;else{raw=m[0];stable=1;}if(stable>=4&&await waitIdle(30000)){await sleep(1500);const m2=finalMatches(await bodyText()).at(-1);if(m2&&m2[0]===raw)return parseFinal(m2);}}await sleep(900);}throw new Error(`TIMEOUT_WAITING_STABLE_DUCK_FINAL_${nonce}`);}
async function dismissTips(){return evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const e=[...document.querySelectorAll('button,[role="button"]')].filter(visible).find(x=>/^got it!?$/i.test(String(x.innerText||x.getAttribute('aria-label')||'').trim()));if(!e)return false;e.click();return true;})()`).catch(()=>false);}
async function freshChat(){await dismissTips();const clicked=await evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const els=[...document.querySelectorAll('button,a,[role="button"]')].filter(visible);const e=els.find(x=>/^new chat(?:\\s|$)/i.test(String(x.innerText||x.getAttribute('aria-label')||'').trim()));if(!e)return false;e.click();return true;})()`);if(!clicked)throw new Error('DUCK_NEW_CHAT_CONTROL_NOT_FOUND');await sleep(1500);await waitComposer();await setComposerValue('');console.log('FRESH_CHAT_READY=true');console.log(`FRESH_CHAT_URL=${(await uiState()).href}`);}

async function main(){
  fs.mkdirSync(OUT_DIR,{recursive:true});
  await waitComposer();
  await freshChat();
  const state=await uiState();
  console.log('=== DUCK AI CERTIFICATION V3 ===');
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
  const cert={test_id:TEST_ID,nonce,provider:'Duck.ai',product:'Duck.ai Web',transport:'browser-session-direct-cdp',tier:state.freeVisible?'Free':'not-confirmed',mode:state.fastVisible?'Fast':'not-confirmed',model_ui:state.model||'not-detected',authenticated:false,fresh_chat:true,streaming_stability_guard:true,submit_handshake:'native-value-setter+input-change-events+send-submit-button+composer-cleared+prompt-visible',api_required:false,zero_cost_path:true,expected:{master:MASTER,sums:SUMS,terms:TERMS,checksum:EXPECTED},actual:final,certified:passed};
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
  console.log('SUBMIT_HANDSHAKE=native-value-setter+input-change-events+send-submit-button');
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
