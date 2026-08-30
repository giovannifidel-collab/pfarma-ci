const CDP=process.env.COPILOT_LAB_CDP_URL||'http://127.0.0.1:9231';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function json(url,opts={}){const r=await fetch(url,opts);if(!r.ok)throw new Error(`HTTP_${r.status}_${url}`);return r.json();}
let targets=await json(`${CDP}/json/list`);
let target=targets.find(t=>t.type==='page'&&/(?:copilot\.com|copilot\.microsoft\.com)/i.test(t.url||''));
if(!target?.webSocketDebuggerUrl)throw new Error('COPILOT_PAGE_NOT_FOUND');
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});});
let seq=0;const pending=new Map();
ws.addEventListener('message',ev=>{let m;try{m=JSON.parse(ev.data);}catch{return;}if(!m.id||!pending.has(m.id))return;const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(new Error(`CDP_${m.error.code}:${m.error.message}`)):p.resolve(m.result||{});});
function call(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evalJs(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}_${r.exceptionDetails.exception?.description||''}`);return r.result?.value;}
await call('Runtime.enable');await call('Page.enable').catch(()=>{});

const prep=await evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const els=[...document.querySelectorAll('button,a,[role="button"]')].filter(visible);const reject=els.find(e=>/^reject$/i.test(String(e.innerText||'').trim()));if(reject)reject.click();const signin=els.find(e=>/^sign in$/i.test(String(e.innerText||'').trim())||/^sign in$/i.test(String(e.getAttribute('aria-label')||'').trim()))||els.find(e=>/sign in to your account/i.test(String(e.innerText||'')));if(!signin)return {clicked:false,href:location.href};signin.click();return {clicked:true,href:location.href,text:String(signin.innerText||signin.getAttribute('aria-label')||'').trim()};})()`);
if(!prep.clicked)throw new Error('COPILOT_VISIBLE_SIGNIN_NOT_FOUND');
await sleep(1500);
let state={};const start=Date.now();
while(Date.now()-start<30000){
  state=await evalJs(`({href:String(location.href||''),title:String(document.title||''),ready:document.readyState,body:String(document.body?.innerText||'').slice(0,3000)})`).catch(()=>({}));
  if(state.href&&state.href!==prep.href)break;
  await sleep(500);
}
console.log('=== COPILOT LOGIN PREP ===');
console.log(`CLICKED_SIGNIN=true`);
console.log(`URL=${state.href||''}`);
console.log(`TITLE=${state.title||''}`);
console.log(`READY_STATE=${state.ready||''}`);
console.log('COPILOT_LOGIN_PREPARED=true');
ws.close();
