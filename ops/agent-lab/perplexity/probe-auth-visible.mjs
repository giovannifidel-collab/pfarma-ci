const CDP=process.env.PERPLEXITY_LAB_CDP_URL||'http://127.0.0.1:9230';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function json(url,opts={}){const r=await fetch(url,opts);if(!r.ok)throw new Error(`HTTP_${r.status}_${url}`);return r.json();}
let targets=await json(`${CDP}/json/list`);
let target=targets.find(t=>t.type==='page'&&/perplexity\.ai/i.test(t.url||''));
if(!target)throw new Error('PERPLEXITY_PAGE_NOT_FOUND');
if(!target.webSocketDebuggerUrl)throw new Error('NO_PERPLEXITY_PAGE_WEBSOCKET');
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});});
let seq=0;const pending=new Map();
ws.addEventListener('message',ev=>{let msg;try{msg=JSON.parse(ev.data);}catch{return;}if(!msg.id||!pending.has(msg.id))return;const p=pending.get(msg.id);pending.delete(msg.id);clearTimeout(p.timer);if(msg.error)p.reject(new Error(`CDP_${msg.error.code}:${msg.error.message}`));else p.resolve(msg.result||{});});
function call(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},20000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evalJs(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}_${r.exceptionDetails.exception?.description||''}`);return r.result?.value;}
await call('Runtime.enable');await sleep(300);
const info=await evalJs(`(()=>{
  const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&Number(s.opacity||1)!==0};
  const text=e=>String(e.innerText||e.textContent||'').trim();
  const composer=[...document.querySelectorAll('[contenteditable="true"],textarea')].filter(visible).map(e=>({tag:e.tagName.toLowerCase(),placeholder:e.getAttribute('placeholder'),aria:e.getAttribute('aria-label'),text:text(e).slice(0,500)}));
  const dialogs=[...document.querySelectorAll('[role="dialog"],dialog,[aria-modal="true"]')].filter(visible).map(e=>({tag:e.tagName.toLowerCase(),role:e.getAttribute('role'),ariaModal:e.getAttribute('aria-modal'),text:text(e).slice(0,4000)}));
  const inputs=[...document.querySelectorAll('input')].filter(visible).map(e=>({type:e.getAttribute('type'),name:e.getAttribute('name'),placeholder:e.getAttribute('placeholder'),aria:e.getAttribute('aria-label')}));
  const buttons=[...document.querySelectorAll('button,[role="button"],a')].filter(visible).map(e=>({text:text(e).slice(0,300),aria:e.getAttribute('aria-label'),href:e.getAttribute('href')})).filter(x=>x.text||x.aria).slice(-120);
  const authWords=x=>/continue with google|continue with apple|enter your email|sign in to perplexity|log in to perplexity|sign in|log in/i.test(String(x||''));
  const visibleAuthDialog=dialogs.some(d=>authWords(d.text));
  const visibleAuthInput=inputs.some(i=>String(i.type||'').toLowerCase()==='email'||/email/i.test(String(i.placeholder||''))||/email/i.test(String(i.aria||'')));
  const visibleAuthButtons=buttons.filter(b=>authWords(b.text)||authWords(b.aria));
  return {href:location.href,title:document.title,composerVisible:composer.length>0,composer,dialogs,inputs,visibleAuthDialog,visibleAuthInput,visibleAuthButtons,AUTH_GATE_VISIBLE:visibleAuthDialog||(visibleAuthInput&&visibleAuthButtons.length>0)};
})()`);
console.log('=== PERPLEXITY AUTH VISIBLE PROBE ===');
console.log(`URL=${info.href}`);
console.log(`TITLE=${info.title}`);
console.log(`COMPOSER_VISIBLE=${info.composerVisible}`);
console.log(`AUTH_GATE_VISIBLE=${info.AUTH_GATE_VISIBLE}`);
console.log(`VISIBLE_AUTH_DIALOG=${info.visibleAuthDialog}`);
console.log(`VISIBLE_AUTH_INPUT=${info.visibleAuthInput}`);
console.log(`VISIBLE_AUTH_BUTTONS=${JSON.stringify(info.visibleAuthButtons,null,2)}`);
console.log(`DIALOGS=${JSON.stringify(info.dialogs,null,2)}`);
console.log(`INPUTS=${JSON.stringify(info.inputs,null,2)}`);
ws.close();