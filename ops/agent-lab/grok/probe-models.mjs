const CDP=process.env.GROK_LAB_CDP_URL||'http://127.0.0.1:9226';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

async function json(url){
  const r=await fetch(url);
  if(!r.ok) throw new Error(`HTTP_${r.status}_${url}`);
  return r.json();
}

const targets=await json(`${CDP}/json/list`);
const target=targets.find(t=>t.type==='page' && /grok\.com/i.test(t.url||''));
if(!target) throw new Error(`NO_GROK_PAGE targets=${targets.map(t=>`${t.type}:${t.url}`).join(' | ')}`);
if(!target.webSocketDebuggerUrl) throw new Error('NO_GROK_PAGE_WEBSOCKET');

const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);
  ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});
  ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});
});

let seq=0;
const pending=new Map();
ws.addEventListener('message',ev=>{
  let msg; try{msg=JSON.parse(ev.data);}catch{return;}
  if(!msg.id || !pending.has(msg.id)) return;
  const {resolve,reject,timer}=pending.get(msg.id); pending.delete(msg.id); clearTimeout(timer);
  if(msg.error) reject(new Error(`CDP_${msg.error.code}:${msg.error.message}`));
  else resolve(msg.result||{});
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
  if(r.exceptionDetails) throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}`);
  return r.result?.value;
}

await call('Runtime.enable');
console.log('=== GROK MODEL PROBE ===');
console.log(`URL=${target.url}`);

const found=await evalJs(`(()=>{
  const visible=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0};
  const b=[...document.querySelectorAll('button')].find(x=>x.getAttribute('aria-label')==='Model select'&&visible(x));
  if(!b)return false;
  b.click();
  return true;
})()`);
console.log(`MODEL_SELECT_FOUND=${found}`);
if(!found){ws.close();process.exit(2);}
await sleep(1200);

const result=await evalJs(`(()=>{
 const visible=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0};
 const selectors=['[role="menuitem"]','[role="option"]','[role="menu"] button','[role="listbox"] button','[data-radix-menu-content] button','[data-radix-popper-content-wrapper] button'];
 let items=[];
 for(const sel of selectors){
   const a=[...document.querySelectorAll(sel)].filter(visible).map(e=>({text:(e.innerText||'').trim(),aria:e.getAttribute('aria-label'),disabled:!!e.disabled||e.getAttribute('aria-disabled')==='true'})).filter(x=>x.text||x.aria);
   if(a.length){items=a;break;}
 }
 const lines=(document.body?.innerText||'').split('\\n').map(s=>s.trim()).filter(Boolean);
 const modelLines=lines.filter(s=>/grok|fast|expert|think|model|mini|auto|beta|super/i.test(s)).slice(-100);
 const limitLines=lines.filter(s=>/limit|upgrade|supergrok|hour|minute|quota|wait/i.test(s)).slice(-50);
 const uniq=[]; const seen=new Set();
 for(const it of items){const k=JSON.stringify(it);if(!seen.has(k)){seen.add(k);uniq.push(it)}}
 return {items:uniq,modelLines,limitLines};
})()`);

if(result.items?.length) console.log(`MODEL_OPTIONS=${JSON.stringify(result.items,null,2)}`);
else console.log(`MODEL_LINES=${JSON.stringify(result.modelLines||[],null,2)}`);
console.log(`LIMIT_LINES=${JSON.stringify(result.limitLines||[],null,2)}`);
ws.close();
process.exit(0);
