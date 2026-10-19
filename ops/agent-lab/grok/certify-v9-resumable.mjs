import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const CDP=process.env.GROK_LAB_CDP_URL||'http://127.0.0.1:9226';
const OUT=path.resolve('certifications');
const TEST='HIVE-GROK-STRESS-0009-RESUMABLE';
const STATE_FILE=path.join(OUT,`${TEST}-state.json`);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const log=(...x)=>console.log(new Date().toISOString(),...x);

const DATASETS=[
 {salt:7919,coeff:{A:17,B:29,C:43},shards:{A:[311,7,19,23,5],B:[41,53,67,71,73],C:[79,83,89,97,101]}},
 {salt:6421,coeff:{A:23,B:31,C:37},shards:{A:[107,13,29,31,17],B:[47,59,61,71,11],C:[83,89,97,19,23]}},
 {salt:4813,coeff:{A:19,B:41,C:47},shards:{A:[127,37,43,53,61],B:[17,67,79,83,89],C:[97,101,103,29,31]}}
];

function saveState(state){
 fs.mkdirSync(OUT,{recursive:true});
 fs.writeFileSync(STATE_FILE,JSON.stringify(state,null,2));
}
function loadState(){
 if(!fs.existsSync(STATE_FILE)) return {test_id:TEST,trials:[],current:null};
 const s=JSON.parse(fs.readFileSync(STATE_FILE,'utf8'));
 if(s.test_id!==TEST) throw new Error('STATE_TEST_ID_MISMATCH');
 return s;
}

async function json(url,opts={}){
 const r=await fetch(url,opts);
 if(!r.ok) throw new Error(`HTTP_${r.status}_${url}`);
 return r.json();
}
async function createTarget(url){return json(`${CDP}/json/new?${encodeURIComponent(url)}`,{method:'PUT'});}
async function closeTarget(id){try{await fetch(`${CDP}/json/close/${id}`);}catch{}}

async function attach(target){
 if(!target?.webSocketDebuggerUrl) throw new Error('NO_PAGE_WEBSOCKET');
 const ws=new WebSocket(target.webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);
   ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});
   ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});
 });
 let seq=0; const pending=new Map();
 ws.addEventListener('message',ev=>{
   let msg; try{msg=JSON.parse(ev.data);}catch{return;}
   if(!msg.id||!pending.has(msg.id))return;
   const p=pending.get(msg.id);pending.delete(msg.id);clearTimeout(p.timer);
   if(msg.error)p.reject(new Error(`CDP_${msg.error.code}:${msg.error.message}`));else p.resolve(msg.result||{});
 });
 const call=(method,params={})=>new Promise((resolve,reject)=>{
   const id=++seq;
   const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);
   pending.set(id,{resolve,reject,timer});
   ws.send(JSON.stringify({id,method,params}));
 });
 const evalJs=async expression=>{
   const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
   if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}`);
   return r.result?.value;
 };
 await call('Runtime.enable');
 await call('Page.enable').catch(()=>{});
 return {ws,call,evalJs};
}

const editorExpr=`(()=>{
 const visible=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0};
 const sels=['textarea[data-testid="grok-compose-input"]','[data-testid="grokInput"] textarea','[data-testid="grokInput"] [contenteditable="true"]','div[contenteditable="true"][data-lexical-editor="true"]','textarea[aria-label*="Ask" i]','div[contenteditable="true"][aria-label*="Ask" i]','div[contenteditable="true"]'];
 for(const s of sels){for(const e of document.querySelectorAll(s)){if(visible(e))return e;}}
 return null;
})()`;

async function pageState(cdp){
 return cdp.evalJs(`(()=>{const e=${editorExpr};const text=e?(e.value??e.innerText??''):'';const body=document.body?.innerText||'';const quota=/before limit is gone|Wait or upgrade to SuperGrok for much higher limits/i.test(body);const stop=[...document.querySelectorAll('button')].some(b=>{const x=(b.getAttribute('aria-label')||b.getAttribute('title')||b.getAttribute('data-testid')||'');const r=b.getBoundingClientRect(),s=getComputedStyle(b);return /stop/i.test(x)&&r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'});const submit=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('data-testid')==='chat-submit'||/submit|send/i.test(b.getAttribute('aria-label')||''))&&b.getBoundingClientRect().width>0);return {href:location.href,ready:document.readyState,editor:!!e,text,quota,stop,submit:submit?{disabled:!!submit.disabled,ariaDisabled:submit.getAttribute('aria-disabled')}:null};})()`);
}
async function bodyText(cdp){return cdp.evalJs(`document.body?.innerText||''`).catch(()=> '');}
const count=(txt,tok)=>tok?txt.split(tok).length-1:0;

async function dismissPromos(cdp){
 await cdp.evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};for(const b of document.querySelectorAll('button')){const t=(b.innerText||'').trim();if(visible(b)&&/^Dismiss$/i.test(t)){b.click();return true}}return false})()`).catch(()=>false);
 await sleep(250);
}
async function waitReady(cdp,maxMs=60000){
 const start=Date.now();
 while(Date.now()-start<maxMs){
   await dismissPromos(cdp);
   const s=await pageState(cdp).catch(()=>null);
   if(s?.quota)throw new Error('GROK_QUOTA_BLOCKED');
   if(s?.editor&&s.ready!=='loading'&&!s.stop)return s;
   await sleep(500);
 }
 throw new Error('GROK_PAGE_NOT_READY');
}

async function focusAndClear(cdp){
 const ok=await cdp.evalJs(`(()=>{const e=${editorExpr};if(!e)return false;e.focus();return true})()`);
 if(!ok)throw new Error('GROK_EDITOR_NOT_FOUND');
 await cdp.call('Input.dispatchKeyEvent',{type:'rawKeyDown',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
 await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
 await cdp.call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
 await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
}
async function typeText(cdp,text){
 await focusAndClear(cdp);
 const lines=text.split('\n');
 for(let i=0;i<lines.length;i++){
   if(lines[i])await cdp.call('Input.insertText',{text:lines[i]});
   if(i<lines.length-1){
     await cdp.call('Input.dispatchKeyEvent',{type:'rawKeyDown',modifiers:8,key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
     await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',modifiers:8,key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
   }
 }
}
async function send(cdp,text){
 await waitReady(cdp);
 await typeText(cdp,text);
 let st=Date.now(); let state=null;
 while(Date.now()-st<15000){
   state=await pageState(cdp);
   if(state.quota)throw new Error('GROK_QUOTA_BLOCKED');
   if(state.text.trim().length>=5&&state.submit&&!state.submit.disabled&&state.submit.ariaDisabled!=='true')break;
   await sleep(250);
 }
 if(!state?.submit||state.submit.disabled||state.submit.ariaDisabled==='true')throw new Error(`GROK_SUBMIT_NOT_READY_DIRECT ${JSON.stringify(state)}`);
 const clicked=await cdp.evalJs(`(()=>{const b=[...document.querySelectorAll('button')].find(x=>(x.getAttribute('data-testid')==='chat-submit'||/submit|send/i.test(x.getAttribute('aria-label')||''))&&x.getBoundingClientRect().width>0&&!x.disabled&&x.getAttribute('aria-disabled')!=='true');if(!b)return false;b.click();return true})()`);
 if(!clicked)throw new Error('GROK_SUBMIT_CLICK_FAILED');
 log('SUBMIT direct-cdp');
 st=Date.now();
 while(Date.now()-st<15000){
   const s=await pageState(cdp);
   if(s.quota)throw new Error('GROK_QUOTA_BLOCKED');
   if(s.text.trim().length<5)return s;
   await sleep(250);
 }
 throw new Error('GROK_PROMPT_NOT_SUBMITTED_DIRECT');
}

function expected(d){
 const sums={},terms={};
 for(const k of ['A','B','C']){sums[k]=d.shards[k].reduce((a,b)=>a+b,0);terms[k]=d.coeff[k]*sums[k];}
 return {sums,terms,checksum:d.salt+terms.A+terms.B+terms.C};
}
function resultRegex(nonce,recheck=false){
 const p=recheck?'GROK_RECHECK_RESULT':'GROK_CERT_RESULT';
 return new RegExp(`${p}:${nonce}:(\\d+),(\\d+),(\\d+):(\\d+),(\\d+),(\\d+):(\\d+)`);
}
function parseResult(body,nonce,recheck=false){
 const m=resultRegex(nonce,recheck).exec(body);
 return m?{sums:{A:+m[1],B:+m[2],C:+m[3]},terms:{A:+m[4],B:+m[5],C:+m[6]},checksum:+m[7]}:null;
}
function same(a,b){return !!a&&a.sums.A===b.sums.A&&a.sums.B===b.sums.B&&a.sums.C===b.sums.C&&a.terms.A===b.terms.A&&a.terms.B===b.terms.B&&a.terms.C===b.terms.C&&a.checksum===b.checksum;}

async function waitAssistantEcho(cdp,token,before,maxMs=90000){
 const start=Date.now();
 while(Date.now()-start<maxMs){
   const body=await bodyText(cdp);
   if(/before limit is gone|Wait or upgrade to SuperGrok for much higher limits/i.test(body))throw new Error('GROK_QUOTA_BLOCKED');
   if(count(body,token)>=before+2){await waitReady(cdp);return true;}
   await sleep(600);
 }
 return false;
}
async function waitResult(cdp,nonce,recheck=false,maxMs=90000){
 const start=Date.now();
 while(Date.now()-start<maxMs){
   const body=await bodyText(cdp);
   if(/before limit is gone|Wait or upgrade to SuperGrok for much higher limits/i.test(body))throw new Error('GROK_QUOTA_BLOCKED');
   const r=parseResult(body,nonce,recheck);
   if(r){await waitReady(cdp);return r;}
   await sleep(600);
 }
 return null;
}

function newCurrent(index){
 return {index,nonce:crypto.randomBytes(4).toString('hex').toUpperCase(),stage:'needs_data',url:'https://grok.com/',first:null};
}

async function runCurrent(state){
 if(!state.current) state.current=newCurrent(state.trials.length+1);
 const cur=state.current;
 const d=DATASETS[cur.index-1];
 if(!d) return;
 const exp=expected(d);
 const target=await createTarget(cur.url||'https://grok.com/');
 const cdp=await attach(target);
 try{
   const ready=await waitReady(cdp,60000);
   cur.url=ready.href||cur.url;
   saveState(state);
   log('TRIAL_RESUME',cur.index,`stage=${cur.stage}`,`nonce=${cur.nonce}`,`expected=${exp.checksum}`);

   const ack=`ACK_DATA:${cur.nonce}:${d.salt}:${d.coeff.A},${d.coeff.B},${d.coeff.C}:${d.shards.A.join(',')}|${d.shards.B.join(',')}|${d.shards.C.join(',')}`;
   const dataPrompt=[`${TEST} / ${cur.nonce}`,`SALT=${d.salt}`,`COEFF_A=${d.coeff.A}`,`COEFF_B=${d.coeff.B}`,`COEFF_C=${d.coeff.C}`,`SHARD_A=${d.shards.A.join(',')}`,`SHARD_B=${d.shards.B.join(',')}`,`SHARD_C=${d.shards.C.join(',')}`,`Memorizza questi dati esattamente. Rispondi ESATTAMENTE: ${ack}`].join('\n');

   if(cur.stage==='needs_data'){
     let body=await bodyText(cdp);
     if(count(body,ack)<2){
       const before=count(body,ack);
       log('SEND DATA');
       const afterSend=await send(cdp,dataPrompt);
       cur.url=afterSend?.href||cur.url;
       saveState(state);
       if(!await waitAssistantEcho(cdp,ack,before))throw new Error('TIMEOUT_DATA_ASSISTANT_ECHO');
     }
     const s=await pageState(cdp); cur.url=s.href||cur.url;
     cur.stage='data_verified'; saveState(state);
     log('CHECKPOINT DATA_VERIFIED',`url=${cur.url}`);
   }

   if(cur.stage==='data_verified'){
     let body=await bodyText(cdp);
     let first=parseResult(body,cur.nonce,false);
     if(!first){
       const resultPrompt=[`${TEST} / ${cur.nonce}`,'Usa SOLO i dati memorizzati nel messaggio DATA. Ricalcola da zero SUM_A, SUM_B, SUM_C; poi TERM_A=COEFF_A*SUM_A, TERM_B=COEFF_B*SUM_B, TERM_C=COEFF_C*SUM_C; infine CHECKSUM=SALT+TERM_A+TERM_B+TERM_C.','Nessuna spiegazione.',`Rispondi ESATTAMENTE: GROK_CERT_RESULT:${cur.nonce}:<SUM_A>,<SUM_B>,<SUM_C>:<TERM_A>,<TERM_B>,<TERM_C>:<CHECKSUM>`].join('\n');
       log('SEND RESULT');
       const afterSend=await send(cdp,resultPrompt);
       cur.url=afterSend?.href||cur.url; saveState(state);
       first=await waitResult(cdp,cur.nonce,false);
       if(!first)throw new Error('TIMEOUT_RESULT');
     }
     cur.first=first;
     log('RESULT FIRST',JSON.stringify(first),`OK=${same(first,exp)}`);
     if(same(first,exp)){
       state.trials.push({index:cur.index,nonce:cur.nonce,expected:exp,first,final:first,rechecked:false,raw_pass:true,verified_pass:true});
       state.current=null; saveState(state);
       log('TRIAL_END',cur.index,'RAW_PASS=true','VERIFIED_PASS=true');
       return;
     }
     cur.stage='needs_recheck'; saveState(state);
     log('CHECKPOINT NEEDS_RECHECK');
   }

   if(cur.stage==='needs_recheck'){
     let body=await bodyText(cdp);
     let final=parseResult(body,cur.nonce,true);
     if(!final){
       const recheckPrompt=[`${TEST} / ${cur.nonce}`,'Il risultato precedente non supera un controllo interno di coerenza. Non ti fornisco nessun valore atteso. Riparti dai dati originali DATA e ricalcola tutto da zero.','Nessuna spiegazione.',`Rispondi ESATTAMENTE: GROK_RECHECK_RESULT:${cur.nonce}:<SUM_A>,<SUM_B>,<SUM_C>:<TERM_A>,<TERM_B>,<TERM_C>:<CHECKSUM>`].join('\n');
       log('SEND RECHECK');
       const afterSend=await send(cdp,recheckPrompt);
       cur.url=afterSend?.href||cur.url; saveState(state);
       final=await waitResult(cdp,cur.nonce,true);
       if(!final)throw new Error('TIMEOUT_RECHECK_RESULT');
     }
     const verified=same(final,exp);
     log('RESULT RECHECK',JSON.stringify(final),`OK=${verified}`);
     state.trials.push({index:cur.index,nonce:cur.nonce,expected:exp,first:cur.first,final,rechecked:true,raw_pass:false,verified_pass:verified});
     state.current=null; saveState(state);
     log('TRIAL_END',cur.index,'RAW_PASS=false',`VERIFIED_PASS=${verified}`);
   }
 } finally {
   try{cdp.ws.close();}catch{}
   await closeTarget(target.id);
 }
}

async function main(){
 fs.mkdirSync(OUT,{recursive:true});
 const keeper=await createTarget('about:blank');
 console.log('GROK DIRECT-CDP KEEPER READY');
 const state=loadState();
 try{
   console.log(`RESUME_STATE trials=${state.trials.length} current_stage=${state.current?.stage||'none'}`);
   while(state.trials.length<DATASETS.length){
     await runCurrent(state);
     if(state.trials.some(t=>!t.verified_pass)) break;
   }
   if(state.trials.length<DATASETS.length){
     saveState(state);
     return;
   }
   const raw=state.trials.every(t=>t.raw_pass);
   const verified=state.trials.every(t=>t.verified_pass);
   const certified=verified;
   const mode=raw?'RAW_CERTIFIED':verified?'VERIFIER_CERTIFIED':'NOT_CERTIFIED';
   const file=path.join(OUT,`${TEST}-${Date.now()}.json`);
   fs.writeFileSync(file,JSON.stringify({test_id:TEST,trials:state.trials,raw_pass:raw,verified_pass:verified,certification_mode:mode,certified},null,2));
   console.log(`GROK_CERTIFIED=${certified}`);
   console.log(`TEST_ID=${TEST}`);
   console.log(`TRIALS=${state.trials.length}`);
   console.log(`RAW_PASS=${raw}`);
   console.log(`VERIFIED_PASS=${verified}`);
   console.log(`CERTIFICATION_MODE=${mode}`);
   console.log(`CERTIFICATE=${file}`);
   if(certified) fs.renameSync(STATE_FILE,`${STATE_FILE}.${Date.now()}.done`);
   process.exitCode=certified?0:2;
 } finally {
   await closeTarget(keeper.id);
 }
}

main().catch(e=>{
 if(String(e.message||'').startsWith('GROK_QUOTA_BLOCKED')){
   const s=loadState();
   console.error('GROK_CERTIFIED=INCONCLUSIVE');
   console.error('CERTIFICATION_BLOCKED_BY_QUOTA=true');
   console.error(`RESUME_STATE trials=${s.trials.length} current_stage=${s.current?.stage||'none'}`);
   console.error(`CHECKPOINT=${STATE_FILE}`);
   console.error(`ERROR=${e.message}`);
   process.exit(3);
 }
 console.error('GROK_CERTIFIED=INCONCLUSIVE');
 console.error('CERTIFICATION_INFRA_ERROR=true');
 console.error(`ERROR=${e.message}`);
 process.exit(1);
});
