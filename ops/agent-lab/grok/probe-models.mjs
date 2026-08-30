const CDP=process.env.GROK_LAB_CDP_URL||'http://127.0.0.1:9226';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

async function json(url,opts={}){
  const r=await fetch(url,opts);
  if(!r.ok) throw new Error(`HTTP_${r.status}_${url}`);
  return r.json();
}

let targets=await json(`${CDP}/json/list`);
let target=targets.find(t=>t.type==='page' && /grok\.com/i.test(t.url||''));

if(!target){
  console.log('GROK_PAGE_MISSING=true');
  console.log('GROK_PAGE_CREATE=true');
  target=await json(`${CDP}/json/new?${encodeURIComponent('https://grok.com/')}`,{method:'PUT'});
  if(!target?.webSocketDebuggerUrl) throw new Error(`GROK_PAGE_CREATE_FAILED ${JSON.stringify(target)}`);
  await sleep(2500);
}

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
await call('Page.enable').catch(()=>{});

const readyStart=Date.now();
let state={href:'',ready:''};
while(Date.now()-readyStart<45000){
  state=await evalJs(`({href:location.href,ready:document.readyState})`).catch(()=>({href:'',ready:''}));
  if(/grok\.com/i.test(state.href||'') && state.ready!=='loading') break;
  await sleep(500);
}

console.log('=== GROK MODEL PROBE ===');
console.log(`URL=${state.href||target.url||''}`);
console.log(`READY_STATE=${state.ready||''}`);

const modelStart=Date.now();
let found=false;
while(Date.now()-modelStart<30000){
  found=await evalJs(`(()=>{
    const visible=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0};
    const b=[...document.querySelectorAll('button')].find(x=>x.getAttribute('aria-label')==='Model select'&&visible(x));
    if(!b)return false;
    b.click();
    return true;
  })()`).catch(()=>false);
  if(found) break;
  await sleep(600);
}

console.log(`MODEL_SELECT_FOUND=${found}`);
if(!found){
  const body=await evalJs(`document.body?.innerText||''`).catch(()=> '');
  console.log(`BODY_TAIL=${JSON.stringify(String(body).slice(-5000))}`);
  ws.close();
  process.exit(2);
}

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
