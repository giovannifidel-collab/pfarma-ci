const CDP=process.env.DEEPSEEK_LAB_CDP_URL||'http://127.0.0.1:9227';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

async function json(url,opts={}){
  const r=await fetch(url,opts);
  if(!r.ok) throw new Error(`HTTP_${r.status}_${url}`);
  return r.json();
}

const targets=await json(`${CDP}/json/list`);
const candidates=targets.filter(t=>t.type==='page' && /chat\.deepseek\.com/i.test(t.url||''));
const target=candidates.find(t=>!/(?:\/sign_in)(?:\?|$)/i.test(t.url||''))||candidates[0];
if(!target?.webSocketDebuggerUrl) throw new Error('NO_AUTHENTICATED_DEEPSEEK_PAGE');

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
function call(method,params={}){
  const id=++seq;
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},20000);
    pending.set(id,{resolve,reject,timer});
    ws.send(JSON.stringify({id,method,params}));
  });
}
async function evalJs(expression){
  const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}`);
  return r.result?.value;
}
await call('Runtime.enable');
await sleep(1500);

const info=await evalJs(`(()=>{
  const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
  const names=['Instant','Expert','Vision','DeepThink','Search'];
  const out=[];
  for(const e of document.querySelectorAll('body *')){
    if(!visible(e)) continue;
    const text=(e.innerText||'').trim();
    if(!names.includes(text)) continue;
    const r=e.getBoundingClientRect(),s=getComputedStyle(e);
    out.push({
      text,
      tag:e.tagName.toLowerCase(),
      role:e.getAttribute('role'),
      tabindex:e.getAttribute('tabindex'),
      ariaPressed:e.getAttribute('aria-pressed'),
      ariaSelected:e.getAttribute('aria-selected'),
      dataState:e.getAttribute('data-state'),
      className:String(e.className||'').slice(0,500),
      cursor:s.cursor,
      x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height),
      parentTag:e.parentElement?.tagName?.toLowerCase()||null,
      parentRole:e.parentElement?.getAttribute('role')||null,
      parentText:(e.parentElement?.innerText||'').trim().slice(0,300),
      html:e.outerHTML.slice(0,1200)
    });
  }
  return {href:location.href,title:document.title,modes:out};
})()`);

console.log('=== DEEPSEEK MODE PROBE ===');
console.log(`URL=${info.href}`);
console.log(`TITLE=${info.title}`);
console.log(`MODES=${JSON.stringify(info.modes,null,2)}`);
ws.close();
