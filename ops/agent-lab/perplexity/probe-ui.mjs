const CDP=process.env.PERPLEXITY_LAB_CDP_URL||'http://127.0.0.1:9230';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

async function json(url,opts={}){const r=await fetch(url,opts);if(!r.ok)throw new Error(`HTTP_${r.status}_${url}`);return r.json();}
let targets=await json(`${CDP}/json/list`);
let target=targets.find(t=>t.type==='page'&&/perplexity\.ai/i.test(t.url||''));
if(!target){target=await json(`${CDP}/json/new?${encodeURIComponent('https://www.perplexity.ai/')}`,{method:'PUT'});await sleep(2500);}
if(!target?.webSocketDebuggerUrl)throw new Error('NO_PERPLEXITY_PAGE_WEBSOCKET');

const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});});
let seq=0;const pending=new Map();
ws.addEventListener('message',ev=>{let msg;try{msg=JSON.parse(ev.data);}catch{return;}if(!msg.id||!pending.has(msg.id))return;const p=pending.get(msg.id);pending.delete(msg.id);clearTimeout(p.timer);if(msg.error)p.reject(new Error(`CDP_${msg.error.code}:${msg.error.message}`));else p.resolve(msg.result||{});});
function call(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},20000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evalJs(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}_${r.exceptionDetails.exception?.description||''}`);return r.result?.value;}
await call('Runtime.enable');await call('Page.enable').catch(()=>{});

const start=Date.now();while(Date.now()-start<30000){const ready=await evalJs(`document.readyState`).catch(()=> '');if(ready&&ready!=='loading')break;await sleep(500);}await sleep(1800);
const info=await evalJs(`(()=>{
  const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
  const body=String(document.body?.innerText||'');
  const low=body.toLowerCase();
  const controls=[...document.querySelectorAll('textarea,input,[contenteditable="true"]')].filter(visible).map(e=>({tag:e.tagName.toLowerCase(),type:e.getAttribute('type'),placeholder:e.getAttribute('placeholder'),aria:e.getAttribute('aria-label'),contenteditable:e.getAttribute('contenteditable')})).slice(-60);
  const buttons=[...document.querySelectorAll('button,[role="button"]')].filter(visible).map(e=>({text:String(e.innerText||'').trim(),aria:e.getAttribute('aria-label'),title:e.getAttribute('title'),pressed:e.getAttribute('aria-pressed')})).filter(x=>x.text||x.aria||x.title).slice(-100);
  const login=location.href.includes('/login')||location.href.includes('/signin')||low.includes('continue with google')||low.includes('continue with apple')||low.includes('sign in to perplexity');
  const chat=controls.some(x=>x.tag==='textarea'||x.contenteditable==='true')&&(low.includes('perplexity')||low.includes('ask anything')||low.includes('what do you want to know')||low.includes('search'));
  return {href:location.href,title:document.title,ready:document.readyState,login,chat,controls,buttons,tail:body.slice(-12000)};
})()`);
console.log('=== PERPLEXITY UI PROBE ===');
console.log(`URL=${info.href}`);console.log(`TITLE=${info.title}`);console.log(`READY_STATE=${info.ready}`);console.log(`LOGIN_HINT=${info.login}`);console.log(`CHAT_HINT=${info.chat}`);console.log(`CONTROLS=${JSON.stringify(info.controls,null,2)}`);console.log(`BUTTONS=${JSON.stringify(info.buttons,null,2)}`);console.log(`BODY_TAIL=${JSON.stringify(info.tail)}`);
ws.close();
