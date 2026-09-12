import fs from 'node:fs';
import path from 'node:path';

const CDP=process.env.GROK_LAB_CDP_URL||'http://127.0.0.1:9226';
const OUT=path.resolve('certifications');
const TEST='HIVE-GROK-STRESS-0009-RESUMABLE';
const STATE_FILE=path.join(OUT,`${TEST}-state.json`);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

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

if(!fs.existsSync(STATE_FILE)) throw new Error(`NO_CHECKPOINT ${STATE_FILE}`);
const state=JSON.parse(fs.readFileSync(STATE_FILE,'utf8'));
const cur=state.current;
if(!cur) throw new Error('NO_CURRENT_TRIAL_IN_CHECKPOINT');

console.log('=== GROK CHECKPOINT PROBE ===');
console.log(`TEST_ID=${state.test_id}`);
console.log(`TRIALS_DONE=${state.trials?.length||0}`);
console.log(`CURRENT_INDEX=${cur.index}`);
console.log(`CURRENT_STAGE=${cur.stage}`);
console.log(`NONCE=${cur.nonce}`);
console.log(`CHECKPOINT_URL=${cur.url}`);

const target=await createTarget(cur.url||'https://grok.com/');
const cdp=await attach(target);
try{
  const started=Date.now();
  let reloaded=false;
  let restored=false;
  let lastBody='';
  while(Date.now()-started<45000){
    lastBody=await cdp.evalJs(`document.body?.innerText||''`).catch(()=> '');
    if(lastBody.includes(cur.nonce)){
      restored=true;
      break;
    }
    if(!reloaded && Date.now()-started>15000){
      console.log('CHECKPOINT_RELOAD=true');
      await cdp.call('Page.reload',{ignoreCache:false}).catch(()=>{});
      reloaded=true;
    }
    await sleep(1000);
  }

  const info=await cdp.evalJs(`(()=>{
    const body=document.body?.innerText||'';
    const lines=body.split('\\n').map(s=>s.trim()).filter(Boolean);
    const nonce=${JSON.stringify(cur.nonce)};
    const interesting=lines.filter(s=>
      s.includes(nonce)||
      /GROK_(?:RECHECK_)?CERT_RESULT|GROK_RECHECK_RESULT/i.test(s)||
      /limit|quota|upgrade|supergrok|wait|try again|hour|minute|too many|usage/i.test(s)
    ).slice(-120);
    const buttons=[...document.querySelectorAll('button')].map(b=>({
      text:(b.innerText||'').trim(),
      aria:b.getAttribute('aria-label'),
      testid:b.getAttribute('data-testid'),
      disabled:!!b.disabled,
      ariaDisabled:b.getAttribute('aria-disabled')
    })).filter(x=>x.aria||x.testid||x.text).slice(-80);
    const candidates=lines.filter(s=>s.includes('GROK_')||s.includes(nonce)).slice(-80);
    return {href:location.href,ready:document.readyState,interesting,candidates,buttons,tail:body.slice(-12000),title:document.title};
  })()`);
  console.log(`URL=${info.href}`);
  console.log(`TITLE=${info.title}`);
  console.log(`READY_STATE=${info.ready}`);
  console.log(`CONTEXT_RESTORED=${restored}`);
  console.log(`WAITED_MS=${Date.now()-started}`);
  console.log(`CANDIDATE_LINES=${JSON.stringify(info.candidates,null,2)}`);
  console.log(`INTERESTING_LINES=${JSON.stringify(info.interesting,null,2)}`);
  console.log(`BUTTONS=${JSON.stringify(info.buttons,null,2)}`);
  console.log(`BODY_TAIL=${JSON.stringify(info.tail)}`);
} finally {
  try{cdp.ws?.close();}catch{}
  await closeTarget(target.id);
}
