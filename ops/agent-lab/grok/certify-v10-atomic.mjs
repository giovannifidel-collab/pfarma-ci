import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const CDP=process.env.GROK_LAB_CDP_URL||'http://127.0.0.1:9226';
const OUT=path.resolve('certifications');
const TEST='HIVE-GROK-STRESS-0010-ATOMIC';
const STATE_FILE=path.join(OUT,`${TEST}-state.json`);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const log=(...x)=>console.log(new Date().toISOString(),...x);

const DATASETS=[
 {salt:7919,coeff:{A:17,B:29,C:43},shards:{A:[311,7,19,23,5],B:[41,53,67,71,73],C:[79,83,89,97,101]}},
 {salt:6421,coeff:{A:23,B:31,C:37},shards:{A:[107,13,29,31,17],B:[47,59,61,71,11],C:[83,89,97,19,23]}},
 {salt:4813,coeff:{A:19,B:41,C:47},shards:{A:[127,37,43,53,61],B:[17,67,79,83,89],C:[97,101,103,29,31]}}
];

function expected(d){
 const sums={},terms={};
 for(const k of ['A','B','C']){sums[k]=d.shards[k].reduce((a,b)=>a+b,0);terms[k]=d.coeff[k]*sums[k];}
 return {sums,terms,checksum:d.salt+terms.A+terms.B+terms.C};
}
function same(a,b){return !!a&&a.sums.A===b.sums.A&&a.sums.B===b.sums.B&&a.sums.C===b.sums.C&&a.terms.A===b.terms.A&&a.terms.B===b.terms.B&&a.terms.C===b.terms.C&&a.checksum===b.checksum;}
function saveState(s){fs.mkdirSync(OUT,{recursive:true});fs.writeFileSync(STATE_FILE,JSON.stringify(s,null,2));}
function loadState(){
 if(!fs.existsSync(STATE_FILE))return {test_id:TEST,trials:[],current:null};
 const s=JSON.parse(fs.readFileSync(STATE_FILE,'utf8'));
 if(s.test_id!==TEST)throw new Error('STATE_TEST_ID_MISMATCH');
 return s;
}

async function json(url,opts={}){const r=await fetch(url,opts);if(!r.ok)throw new Error(`HTTP_${r.status}_${url}`);return r.json();}
async function createTarget(url){return json(`${CDP}/json/new?${encodeURIComponent(url)}`,{method:'PUT'});}
async function closeTarget(id){try{await fetch(`${CDP}/json/close/${id}`);}catch{}}

async function attach(target){
 if(!target?.webSocketDebuggerUrl)throw new Error('NO_PAGE_WEBSOCKET');
 const ws=new WebSocket(target.webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);
  ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});
  ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});
 });
 let seq=0;const pending=new Map();
 ws.addEventListener('message',ev=>{
  let msg;try{msg=JSON.parse(ev.data);}catch{return;}
  if(!msg.id||!pending.has(msg.id))return;
  const p=pending.get(msg.id);pending.delete(msg.id);clearTimeout(p.timer);
  if(msg.error)p.reject(new Error(`CDP_${msg.error.code}:${msg.error.message}`));else p.resolve(msg.result||{});
 });
 const call=(method,params={})=>new Promise((resolve,reject)=>{
  const id=++seq;const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);
  pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));
 });
 const evalJs=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}`);return r.result?.value;};
 await call('Runtime.enable');await call('Page.enable').catch(()=>{});
 return {ws,call,evalJs};
}

const editorExpr=`(()=>{const visible=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0};const sels=['textarea[data-testid="grok-compose-input"]','[data-testid="grokInput"] textarea','[data-testid="grokInput"] [contenteditable="true"]','div[contenteditable="true"][data-lexical-editor="true"]','textarea[aria-label*="Ask" i]','div[contenteditable="true"][aria-label*="Ask" i]','div[contenteditable="true"]'];for(const s of sels){for(const e of document.querySelectorAll(s)){if(visible(e))return e;}}return null;})()`;
const quotaRe=/before limit is gone|wait or upgrade to supergrok|rate limit|usage limit|too many requests|quota exceeded/i;
async function bodyText(cdp){return cdp.evalJs(`document.body?.innerText||''`).catch(()=> '');}
async function dismissPromos(cdp){await cdp.evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};for(const b of document.querySelectorAll('button')){if(visible(b)&&/^Dismiss$/i.test((b.innerText||'').trim())){b.click();return true}}return false})()`).catch(()=>false);}
async function pageState(cdp){return cdp.evalJs(`(()=>{const e=${editorExpr};const body=document.body?.innerText||'';const submit=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('data-testid')==='chat-submit'||/submit|send/i.test(b.getAttribute('aria-label')||''))&&b.getBoundingClientRect().width>0);const stop=[...document.querySelectorAll('button')].some(b=>/stop/i.test((b.getAttribute('aria-label')||b.getAttribute('title')||b.getAttribute('data-testid')||''))&&b.getBoundingClientRect().width>0);return {href:location.href,ready:document.readyState,editor:!!e,text:e?(e.value??e.innerText??''):'',body,stop,submit:submit?{disabled:!!submit.disabled,ariaDisabled:submit.getAttribute('aria-disabled')}:null};})()`);}
async function waitReady(cdp,maxMs=60000){
 const start=Date.now();
 while(Date.now()-start<maxMs){await dismissPromos(cdp);const s=await pageState(cdp).catch(()=>null);if(s&&quotaRe.test(s.body||''))throw new Error('GROK_QUOTA_BLOCKED');if(s?.editor&&s.ready!=='loading'&&!s.stop)return s;await sleep(500);}throw new Error('GROK_PAGE_NOT_READY');
}
async function focusAndClear(cdp){
 const ok=await cdp.evalJs(`(()=>{const e=${editorExpr};if(!e)return false;e.focus();return true})()`);if(!ok)throw new Error('GROK_EDITOR_NOT_FOUND');
 await cdp.call('Input.dispatchKeyEvent',{type:'rawKeyDown',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});await cdp.call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
}
async function typeText(cdp,text){
 await focusAndClear(cdp);const lines=text.split('\n');
 for(let i=0;i<lines.length;i++){if(lines[i])await cdp.call('Input.insertText',{text:lines[i]});if(i<lines.length-1){await cdp.call('Input.dispatchKeyEvent',{type:'rawKeyDown',modifiers:8,key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',modifiers:8,key:'Enter',code:'Enter',windowsVirtualKeyCode:13});}}
}
async function send(cdp,text,onSubmitted){
 await waitReady(cdp);await typeText(cdp,text);let s=null;const start=Date.now();
 while(Date.now()-start<15000){s=await pageState(cdp);if(quotaRe.test(s.body||''))throw new Error('GROK_QUOTA_BLOCKED');if(s.text.trim().length>=5&&s.submit&&!s.submit.disabled&&s.submit.ariaDisabled!=='true')break;await sleep(250);}
 if(!s?.submit||s.submit.disabled||s.submit.ariaDisabled==='true')throw new Error('GROK_SUBMIT_NOT_READY_ATOMIC');
 const clicked=await cdp.evalJs(`(()=>{const b=[...document.querySelectorAll('button')].find(x=>(x.getAttribute('data-testid')==='chat-submit'||/submit|send/i.test(x.getAttribute('aria-label')||''))&&x.getBoundingClientRect().width>0&&!x.disabled&&x.getAttribute('aria-disabled')!=='true');if(!b)return false;b.click();return true})()`);
 if(!clicked)throw new Error('GROK_SUBMIT_CLICK_FAILED');log('SUBMIT atomic-direct-cdp');if(onSubmitted)await onSubmitted();
 const sent=Date.now();while(Date.now()-sent<15000){s=await pageState(cdp);if(quotaRe.test(s.body||''))throw new Error('GROK_QUOTA_BLOCKED');if(s.text.trim().length<5)return s;await sleep(250);}return s;
}

function resultRegex(nonce){return new RegExp(`GROK_ATOMIC_RESULT:${nonce}:(\\d+),(\\d+),(\\d+):(\\d+),(\\d+),(\\d+):(\\d+)`);}
function parseResult(body,nonce){const m=resultRegex(nonce).exec(body);return m?{sums:{A:+m[1],B:+m[2],C:+m[3]},terms:{A:+m[4],B:+m[5],C:+m[6]},checksum:+m[7]}:null;}
async function waitResult(cdp,nonce,maxMs=90000){
 const start=Date.now();let last='';
 while(Date.now()-start<maxMs){last=await bodyText(cdp);if(quotaRe.test(last))throw new Error('GROK_QUOTA_BLOCKED');const r=parseResult(last,nonce);if(r){await waitReady(cdp).catch(()=>{});return {result:r,body:last};}await sleep(600);}return {result:null,body:last};
}
function newCurrent(index){return {index,nonce:crypto.randomBytes(4).toString('hex').toUpperCase(),stage:'needs_send',url:'https://grok.com/'};}

async function runCurrent(state){
 if(!state.current)state.current=newCurrent(state.trials.length+1);
 const cur=state.current,d=DATASETS[cur.index-1],exp=expected(d);if(!d)return;
 const target=await createTarget(cur.url||'https://grok.com/');const cdp=await attach(target);
 try{
  const ready=await waitReady(cdp);cur.url=ready.href||cur.url;saveState(state);
  log('ATOMIC_TRIAL_RESUME',cur.index,`stage=${cur.stage}`,`nonce=${cur.nonce}`,`expected=${exp.checksum}`);
  let body=await bodyText(cdp);let r=parseResult(body,cur.nonce);
  if(!r&&cur.stage==='needs_send'){
   const prompt=[`${TEST} / ${cur.nonce}`,`SALT=${d.salt}`,`COEFF_A=${d.coeff.A}`,`COEFF_B=${d.coeff.B}`,`COEFF_C=${d.coeff.C}`,`SHARD_A=${d.shards.A.join(',')}`,`SHARD_B=${d.shards.B.join(',')}`,`SHARD_C=${d.shards.C.join(',')}`,'In QUESTO STESSO messaggio hai tutti i dati necessari. Calcola da zero: SUM_A, SUM_B, SUM_C; TERM_A=COEFF_A*SUM_A; TERM_B=COEFF_B*SUM_B; TERM_C=COEFF_C*SUM_C; CHECKSUM=SALT+TERM_A+TERM_B+TERM_C.','Nessuna spiegazione.',`Rispondi ESATTAMENTE: GROK_ATOMIC_RESULT:${cur.nonce}:<SUM_A>,<SUM_B>,<SUM_C>:<TERM_A>,<TERM_B>,<TERM_C>:<CHECKSUM>`].join('\n');
   log('SEND ATOMIC');
   await send(cdp,prompt,async()=>{const s=await pageState(cdp).catch(()=>null);cur.stage='sent';cur.url=s?.href||cur.url;saveState(state);log('CHECKPOINT ATOMIC_SENT',`url=${cur.url}`);});
  }
  const waited=await waitResult(cdp,cur.nonce);r=waited.result;
  if(!r){
   const marker=new RegExp(`GROK_ATOMIC_RESULT:${cur.nonce}`,'i').test(waited.body||'');
   if(marker){log('ATOMIC_MALFORMED_RESPONSE');r={sums:{A:NaN,B:NaN,C:NaN},terms:{A:NaN,B:NaN,C:NaN},checksum:NaN};}
   else throw new Error('ATOMIC_RESULT_PENDING_OR_UNRECOGNIZED');
  }
  const pass=same(r,exp);log('ATOMIC_RESULT',JSON.stringify(r),`PASS=${pass}`);
  state.trials.push({index:cur.index,nonce:cur.nonce,expected:exp,result:r,pass});state.current=null;saveState(state);log('ATOMIC_TRIAL_END',cur.index,`PASS=${pass}`);
 } finally {try{cdp.ws.close();}catch{}await closeTarget(target.id);}
}

async function main(){
 fs.mkdirSync(OUT,{recursive:true});const keeper=await createTarget('about:blank');console.log('GROK ATOMIC DIRECT-CDP READY');const state=loadState();
 try{
  console.log(`ATOMIC_RESUME_STATE trials=${state.trials.length} current_stage=${state.current?.stage||'none'}`);
  while(state.trials.length<DATASETS.length){await runCurrent(state);if(state.trials.some(t=>!t.pass))break;}
  if(state.trials.some(t=>!t.pass)){
   console.log('GROK_ATOMIC_CERTIFIED=false');console.log(`TEST_ID=${TEST}`);console.log(`TRIALS_COMPLETED=${state.trials.length}`);console.log('ATOMIC_MODE=FAILED');process.exitCode=2;return;
  }
  if(state.trials.length<DATASETS.length){saveState(state);return;}
  const file=path.join(OUT,`${TEST}-${Date.now()}.json`);fs.writeFileSync(file,JSON.stringify({test_id:TEST,trials:state.trials,atomic_certified:true,mode:'FULL_CONTEXT_ONLY'},null,2));
  console.log('GROK_ATOMIC_CERTIFIED=true');console.log(`TEST_ID=${TEST}`);console.log(`TRIALS_COMPLETED=${state.trials.length}`);console.log('ATOMIC_MODE=FULL_CONTEXT_ONLY');console.log(`CERTIFICATE=${file}`);fs.renameSync(STATE_FILE,`${STATE_FILE}.${Date.now()}.done`);
 } finally {await closeTarget(keeper.id);}
}

main().catch(e=>{
 const s=loadState();
 if(String(e.message||'').startsWith('GROK_QUOTA_BLOCKED')){console.error('GROK_ATOMIC_CERTIFIED=INCONCLUSIVE');console.error('CERTIFICATION_BLOCKED_BY_QUOTA=true');console.error(`ATOMIC_RESUME_STATE trials=${s.trials.length} current_stage=${s.current?.stage||'none'}`);console.error(`CHECKPOINT=${STATE_FILE}`);console.error(`ERROR=${e.message}`);process.exit(3);return;}
 if(String(e.message||'').startsWith('ATOMIC_RESULT_PENDING_OR_UNRECOGNIZED')){console.error('GROK_ATOMIC_CERTIFIED=INCONCLUSIVE');console.error('ATOMIC_RESPONSE_PENDING=true');console.error(`ATOMIC_RESUME_STATE trials=${s.trials.length} current_stage=${s.current?.stage||'none'}`);console.error(`CHECKPOINT=${STATE_FILE}`);console.error(`ERROR=${e.message}`);process.exit(4);return;}
 console.error('GROK_ATOMIC_CERTIFIED=INCONCLUSIVE');console.error('CERTIFICATION_INFRA_ERROR=true');console.error(`ERROR=${e.message}`);process.exit(1);
});
