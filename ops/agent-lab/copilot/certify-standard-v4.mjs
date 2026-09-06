import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const CDP=process.env.COPILOT_LAB_CDP_URL||'http://127.0.0.1:9231';
const OUT_DIR=process.env.COPILOT_LAB_CERT_DIR||path.resolve('certifications');
const TEST_ID='HIVE-COPILOT-STRESS-0004';
const nonce=crypto.randomBytes(4).toString('hex').toUpperCase();
const MASTER={salt:7919,coeff:[17,29,43]};
const SHARDS={A:[311,7,19,23,5],B:[41,53,67,71,73],C:[79,83,89,97,101]};
const SUMS={A:SHARDS.A.reduce((a,b)=>a+b,0),B:SHARDS.B.reduce((a,b)=>a+b,0),C:SHARDS.C.reduce((a,b)=>a+b,0)};
const TERMS={A:MASTER.coeff[0]*SUMS.A,B:MASTER.coeff[1]*SUMS.B,C:MASTER.coeff[2]*SUMS.C};
const EXPECTED=MASTER.salt+TERMS.A+TERMS.B+TERMS.C;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const log=(...x)=>console.log(new Date().toISOString(),...x);

async function json(url){const r=await fetch(url);if(!r.ok)throw new Error(`HTTP_${r.status}_${url}`);return r.json();}
const targets=await json(`${CDP}/json/list`);
const target=targets.find(t=>t.type==='page'&&/copilot\.(com|microsoft\.com)/i.test(t.url||''));
if(!target?.webSocketDebuggerUrl)throw new Error('COPILOT_PAGE_NOT_FOUND');

const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});});
let seq=0;const pending=new Map();
ws.addEventListener('message',ev=>{let msg;try{msg=JSON.parse(ev.data);}catch{return;}if(!msg.id||!pending.has(msg.id))return;const p=pending.get(msg.id);pending.delete(msg.id);clearTimeout(p.timer);msg.error?p.reject(new Error(`CDP_${msg.error.code}:${msg.error.message}`)):p.resolve(msg.result||{});});
function call(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evalJs(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}`);return r.result?.value;}
await call('Runtime.enable');await call('Page.enable').catch(()=>{});

async function bodyText(){return evalJs(`String(document.body?.innerText||'')`).catch(()=> '');}
function literalCount(text,token){return token?text.split(token).length-1:0;}
async function uiState(){return evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const els=[...document.querySelectorAll('button,[role="button"],a')].filter(visible);const composer=[...document.querySelectorAll('[contenteditable="true"],textarea')].filter(visible).find(x=>/message copilot/i.test(x.getAttribute('aria-label')||x.getAttribute('placeholder')||''));const account=els.find(e=>/personal account/i.test(e.getAttribute('aria-label')||''));const send=els.find(e=>/^send$/i.test(String(e.getAttribute('aria-label')||e.innerText||'').trim()));const stop=els.find(e=>/^(stop|stop responding|cancel response)$/i.test(String(e.getAttribute('aria-label')||e.innerText||'').trim()));const text=composer?String(composer.innerText||composer.value||composer.textContent||''):'';const rect=send?send.getBoundingClientRect():null;return {composer:!!composer,composerText:text,account:!!account,sendVisible:!!send,sendDisabled:send?!!send.disabled:null,stopVisible:!!stop,sendRect:rect?{x:rect.x,y:rect.y,w:rect.width,h:rect.height}:null};})()`);}

async function waitResponseIdle(timeout=60000){const start=Date.now();let stable=0;while(Date.now()-start<timeout){const s=await uiState();const ready=s.composer&&!s.stopVisible;if(ready){stable++;if(stable>=5)return true;}else stable=0;await sleep(350);}return false;}
async function waitSendReady(timeout=20000){const start=Date.now();while(Date.now()-start<timeout){const s=await uiState();if(s.composer&&s.sendVisible&&!s.sendDisabled&&s.composerText.includes(nonce))return true;await sleep(250);}return false;}
async function focusComposer(){return evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const e=[...document.querySelectorAll('[contenteditable="true"],textarea')].filter(visible).find(x=>/message copilot/i.test(x.getAttribute('aria-label')||x.getAttribute('placeholder')||''));if(!e)return false;e.focus();return true;})()`);}
async function clearComposer(){if(!await focusComposer())throw new Error('COPILOT_COMPOSER_NOT_FOUND');await call('Input.dispatchKeyEvent',{type:'rawKeyDown',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});await call('Input.dispatchKeyEvent',{type:'keyUp',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});await sleep(250);}
async function clickSendDom(){return evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const e=[...document.querySelectorAll('button,[role="button"]')].filter(visible).find(x=>/^send$/i.test(String(x.getAttribute('aria-label')||x.innerText||'').trim()));if(!e||e.disabled)return false;e.click();return true;})()`);}
async function clickSendMouse(){const s=await uiState();const r=s.sendRect;if(!r||s.sendDisabled)return false;const x=r.x+r.w/2,y=r.y+r.h/2;await call('Input.dispatchMouseEvent',{type:'mouseMoved',x,y,button:'none'});await call('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});await call('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1});return true;}
async function pressEnter(){if(!await focusComposer())return false;await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});return true;}
async function verifySubmitted(stageToken,timeout=9000){const start=Date.now();while(Date.now()-start<timeout){const s=await uiState();const b=await bodyText();if(!s.composerText.includes(nonce)&&literalCount(b,stageToken)>=1)return true;await sleep(250);}return false;}

async function send(text,stageToken,label){
  if(!await waitResponseIdle())throw new Error(`COPILOT_RESPONSE_NOT_IDLE_BEFORE_${label}`);
  await clearComposer();
  await call('Input.insertText',{text});
  await sleep(450);
  let s=await uiState();
  if(!s.composerText.includes(nonce))throw new Error(`COPILOT_TEXT_NOT_INSERTED_${label}`);
  if(!await waitSendReady())throw new Error(`COPILOT_SEND_NOT_READY_AFTER_INSERT_${label}`);

  const attempts=[['DOM_CLICK',clickSendDom],['CDP_MOUSE',clickSendMouse],['ENTER',pressEnter]];
  for(const [name,fn] of attempts){
    if(await verifySubmitted(stageToken,500))return `confirmed-before-${name}`;
    s=await uiState();
    if(!s.composerText.includes(nonce)){
      if(literalCount(await bodyText(),stageToken)>=1)return `submitted-before-${name}`;
      throw new Error(`COPILOT_COMPOSER_LOST_PROMPT_${label}_${name}`);
    }
    if(name!=='ENTER'&&!await waitSendReady(10000))continue;
    log('SUBMIT_ATTEMPT',label,name);
    await fn();
    if(await verifySubmitted(stageToken,10000))return name;
  }
  throw new Error(`COPILOT_PROMPT_NOT_SUBMITTED_AFTER_RETRIES_${stageToken}`);
}

async function waitForExact(expected,before,timeout=180000){const started=Date.now();while(Date.now()-started<timeout){const b=await bodyText();if(literalCount(b,expected)>=before+2){if(!await waitResponseIdle(60000))throw new Error(`COPILOT_RESPONSE_NOT_SETTLED_AFTER_${expected}`);await sleep(1200);return 'body-occurrence-exact+response-idle';}await sleep(750);}throw new Error(`TIMEOUT_WAITING_FOR_EXACT_COPILOT_RESPONSE_${expected}`);}
async function stage(label,prompt,expectedEcho){const before=literalCount(await bodyText(),expectedEcho);log('SEND',label);const method=await send(prompt,expectedEcho,label);log('SUBMITTED',label,method,'composer-cleared+prompt-visible');const validation=await waitForExact(expectedEcho,before);log('PASS',label,validation,'exact-data-echo');}
function parseFinal(m){return {salt:Number(m[1]),coeff:[Number(m[2]),Number(m[3]),Number(m[4])],sums:{A:Number(m[5]),B:Number(m[6]),C:Number(m[7])},terms:{A:Number(m[8]),B:Number(m[9]),C:Number(m[10])},checksum:Number(m[11])};}
function finalMatches(text){const re=new RegExp(`COPILOT_CERT_RESULT:${nonce}:(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+)`,'g');return [...text.matchAll(re)];}
async function waitFinal(timeout=240000){const started=Date.now();let lastRaw='';let stable=0;while(Date.now()-started<timeout){const b=await bodyText();const matches=finalMatches(b);if(matches.length){const m=matches.at(-1),raw=m[0];if(raw===lastRaw)stable++;else{lastRaw=raw;stable=1;}if(stable>=4&&await waitResponseIdle(60000)){await sleep(1800);const m2=finalMatches(await bodyText()).at(-1);if(m2&&m2[0]===raw)return parseFinal(m2);stable=0;}}await sleep(900);}throw new Error(`TIMEOUT_WAITING_FOR_STABLE_COPILOT_CERT_RESULT_${nonce}`);}

async function main(){
  fs.mkdirSync(OUT_DIR,{recursive:true});
  const startedAt=new Date().toISOString();
  if(!await waitResponseIdle(30000))throw new Error('COPILOT_COMPOSER_NOT_READY');
  const state=await uiState();
  log(`START ${TEST_ID} nonce=${nonce} expected=${EXPECTED} sums=${SUMS.A},${SUMS.B},${SUMS.C} terms=${TERMS.A},${TERMS.B},${TERMS.C}`);
  log(`MODE Standard authenticated=${state.account} composer=${state.composer}`);

  const masterEcho=`ACK_MASTER:${nonce}:${MASTER.salt}:${MASTER.coeff.join(',')}`;
  await stage('MASTER',[`${TEST_ID} / ${nonce}`,'Memorizza esattamente questo MASTER per un test multi-turn. Non calcolare ancora il risultato finale.',`SALT=${MASTER.salt}`,`COEFF_A=${MASTER.coeff[0]}`,`COEFF_B=${MASTER.coeff[1]}`,`COEFF_C=${MASTER.coeff[2]}`,`Per confermare i dati ricevuti, rispondi ESATTAMENTE: ${masterEcho}`].join('\n'),masterEcho);
  const echoA=`ACK_A:${nonce}:${SHARDS.A.join(',')}`;await stage('SHARD_A',[`${TEST_ID} / ${nonce}`,`SHARD_A=${SHARDS.A.join(',')}`,`Memorizzalo esattamente e rispondi ESATTAMENTE: ${echoA}`].join('\n'),echoA);
  const echoB=`ACK_B:${nonce}:${SHARDS.B.join(',')}`;await stage('SHARD_B',[`${TEST_ID} / ${nonce}`,`SHARD_B=${SHARDS.B.join(',')}`,`Memorizzalo esattamente e rispondi ESATTAMENTE: ${echoB}`].join('\n'),echoB);
  const echoC=`ACK_C:${nonce}:${SHARDS.C.join(',')}`;await stage('SHARD_C',[`${TEST_ID} / ${nonce}`,`SHARD_C=${SHARDS.C.join(',')}`,`Memorizzalo esattamente e rispondi ESATTAMENTE: ${echoC}`].join('\n'),echoC);

  log('SEND FINAL');
  const finalPrompt=[`${TEST_ID} / ${nonce}`,'Ora usa SOLO il MASTER e i tre shard memorizzati nei messaggi precedenti.','Recupera SALT e coefficienti. Calcola SUM_A, SUM_B, SUM_C. Poi TERM_A=COEFF_A*SUM_A, TERM_B=COEFF_B*SUM_B, TERM_C=COEFF_C*SUM_C. Infine CHECKSUM=SALT+TERM_A+TERM_B+TERM_C.','Non aggiungere spiegazioni.',`Rispondi ESATTAMENTE nel formato: COPILOT_CERT_RESULT:${nonce}:<SALT>:<COEFF_A>:<COEFF_B>:<COEFF_C>:<SUM_A>:<SUM_B>:<SUM_C>:<TERM_A>:<TERM_B>:<TERM_C>:<CHECKSUM>`].join('\n');
  const method=await send(finalPrompt,`COPILOT_CERT_RESULT:${nonce}:`,'FINAL');log('SUBMITTED FINAL',method,'composer-cleared+prompt-visible');
  const final=await waitFinal();
  const passed=final.salt===MASTER.salt&&final.coeff[0]===MASTER.coeff[0]&&final.coeff[1]===MASTER.coeff[1]&&final.coeff[2]===MASTER.coeff[2]&&final.sums.A===SUMS.A&&final.sums.B===SUMS.B&&final.sums.C===SUMS.C&&final.terms.A===TERMS.A&&final.terms.B===TERMS.B&&final.terms.C===TERMS.C&&final.checksum===EXPECTED;
  const cert={test_id:TEST_ID,nonce,provider:'Microsoft Copilot',product:'Microsoft Copilot Web',transport:'browser-session-direct-cdp',mode:'Standard chat',authenticated:state.account,think_deeper_discovered:false,streaming_stability_guard:true,send_handshake:'response-idle(no-stop)+send-ready-after-insert+multi-submit-fallback+composer-cleared+prompt-visible',api_required:false,zero_cost_path:true,started_at:startedAt,completed_at:new Date().toISOString(),expected:{master:MASTER,sums:SUMS,terms:TERMS,checksum:EXPECTED},actual:final,stages:{master:true,shard_a:true,shard_b:true,shard_c:true,final:true},stage_validation:'exact-data-echo',certified:passed};
  const file=path.join(OUT_DIR,`${TEST_ID}-${nonce}.json`);fs.writeFileSync(file,JSON.stringify(cert,null,2));
  console.log('');console.log(`COPILOT_CERTIFIED=${passed?'true':'false'}`);console.log(`TEST_ID=${TEST_ID}`);console.log(`NONCE=${nonce}`);console.log('PRODUCT=Microsoft Copilot Web');console.log('MODE=Standard chat');console.log(`AUTHENTICATED=${state.account?'true':'false'}`);console.log('THINK_DEEPER_DISCOVERED=false');console.log('STREAMING_STABILITY_GUARD=true');console.log('SEND_HANDSHAKE=response-idle+send-ready-after-insert+multi-submit-fallback+composer-cleared+prompt-visible');console.log(`EXPECTED_MASTER=${MASTER.salt}:${MASTER.coeff.join(',')}`);console.log(`ACTUAL_MASTER=${final.salt}:${final.coeff.join(',')}`);console.log(`EXPECTED_SUMS=${SUMS.A},${SUMS.B},${SUMS.C}`);console.log(`ACTUAL_SUMS=${final.sums.A},${final.sums.B},${final.sums.C}`);console.log(`EXPECTED_TERMS=${TERMS.A},${TERMS.B},${TERMS.C}`);console.log(`ACTUAL_TERMS=${final.terms.A},${final.terms.B},${final.terms.C}`);console.log(`EXPECTED_CHECKSUM=${EXPECTED}`);console.log(`ACTUAL_CHECKSUM=${final.checksum}`);console.log(`CERTIFICATE=${file}`);
  ws.close();if(!passed)process.exit(2);
}
main().catch(err=>{console.error('COPILOT_CERTIFIED=false');console.error(`ERROR=${err.message}`);try{ws.close();}catch{}process.exit(1);});
