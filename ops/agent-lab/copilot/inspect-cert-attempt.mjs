const CDP=process.env.COPILOT_LAB_CDP_URL||'http://127.0.0.1:9231';
const NONCE=process.env.COPILOT_CERT_NONCE||'93AA4A37';
const TOKENS={
  master:`ACK_MASTER:${NONCE}:7919:17,29,43`,
  a:`ACK_A:${NONCE}:311,7,19,23,5`,
  shardA:`SHARD_A=311,7,19,23,5`
};
async function json(url){const r=await fetch(url);if(!r.ok)throw new Error(`HTTP_${r.status}_${url}`);return r.json();}
const targets=await json(`${CDP}/json/list`);
const target=targets.find(t=>t.type==='page'&&/copilot\.(com|microsoft\.com)/i.test(t.url||''));
if(!target?.webSocketDebuggerUrl)throw new Error('COPILOT_PAGE_NOT_FOUND');
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});});
let seq=0;const pending=new Map();
ws.addEventListener('message',ev=>{let m;try{m=JSON.parse(ev.data);}catch{return;}if(!m.id||!pending.has(m.id))return;const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(new Error(`CDP_${m.error.code}:${m.error.message}`)):p.resolve(m.result||{});});
function call(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evalJs(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error('EVAL_EXCEPTION');return r.result?.value;}
await call('Runtime.enable');
const state=await evalJs(`(()=>{
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
 const body=String(document.body?.innerText||'');
 const count=t=>t?body.split(t).length-1:0;
 const composer=[...document.querySelectorAll('[contenteditable="true"],textarea')].filter(visible).find(e=>/message copilot/i.test(e.getAttribute('aria-label')||e.getAttribute('placeholder')||''));
 const controls=[...document.querySelectorAll('button,[role="button"]')].filter(visible).map(e=>({text:String(e.innerText||'').trim().slice(0,120),aria:e.getAttribute('aria-label'),title:e.getAttribute('title'),disabled:!!e.disabled,pressed:e.getAttribute('aria-pressed')}));
 const submit=controls.filter(x=>/send|submit|stop generating|stop responding/i.test([x.text,x.aria,x.title].filter(Boolean).join(' ')));
 const hits=[...document.querySelectorAll('body *')].filter(e=>visible(e)&&String(e.innerText||'').includes(${JSON.stringify(NONCE)})).map(e=>({tag:e.tagName,role:e.getAttribute('role'),aria:e.getAttribute('aria-label'),text:String(e.innerText||'').trim().slice(0,1500)})).filter((x,i,a)=>!a.slice(0,i).some(y=>y.text===x.text)).slice(-20);
 return {url:location.href,title:document.title,bodyLen:body.length,masterCount:count(${JSON.stringify(TOKENS.master)}),ackACount:count(${JSON.stringify(TOKENS.a)}),shardACount:count(${JSON.stringify(TOKENS.shardA)}),composerText:composer?String(composer.innerText||composer.value||composer.textContent||''):'',submit,hits,tail:body.slice(-7000)};
})()`);
console.log('=== COPILOT CERT ATTEMPT INSPECTOR ===');
console.log(`NONCE=${NONCE}`);
console.log(`URL=${state.url}`);
console.log(`TITLE=${state.title}`);
console.log(`BODY_LENGTH=${state.bodyLen}`);
console.log(`MASTER_ACK_OCCURRENCES=${state.masterCount}`);
console.log(`SHARD_A_PROMPT_OCCURRENCES=${state.shardACount}`);
console.log(`ACK_A_OCCURRENCES=${state.ackACount}`);
console.log(`COMPOSER_TEXT=${JSON.stringify(state.composerText)}`);
console.log(`SUBMIT_CONTROLS=${JSON.stringify(state.submit,null,2)}`);
console.log(`NONCE_HITS=${JSON.stringify(state.hits,null,2)}`);
console.log(`BODY_TAIL=${JSON.stringify(state.tail)}`);
ws.close();
