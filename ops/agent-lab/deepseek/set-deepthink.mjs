const CDP=process.env.DEEPSEEK_LAB_CDP_URL||'http://127.0.0.1:9227';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

async function json(url,opts={}){
  const r=await fetch(url,opts);
  if(!r.ok) throw new Error(`HTTP_${r.status}_${url}`);
  return r.json();
}

let targets=await json(`${CDP}/json/list`);
let target=targets.find(t=>t.type==='page'&&/chat\.deepseek\.com/i.test(t.url||'')&&!/sign_in/i.test(t.url||''));
if(!target) throw new Error('NO_AUTHENTICATED_DEEPSEEK_PAGE');
if(!target.webSocketDebuggerUrl) throw new Error('NO_DEEPSEEK_PAGE_WEBSOCKET');

const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);
  ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});
  ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});
});

let seq=0; const pending=new Map();
ws.addEventListener('message',ev=>{
  let msg; try{msg=JSON.parse(ev.data);}catch{return;}
  if(!msg.id||!pending.has(msg.id)) return;
  const p=pending.get(msg.id); pending.delete(msg.id); clearTimeout(p.timer);
  if(msg.error)p.reject(new Error(`CDP_${msg.error.code}:${msg.error.message}`)); else p.resolve(msg.result||{});
});
function call(method,params={}){
  const id=++seq;
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);
    pending.set(id,{resolve,reject,timer});
    ws.send(JSON.stringify({id,method,params}));
  });
}
async function evalJs(expression){
  const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(r.exceptionDetails) throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}_${r.exceptionDetails.exception?.description||''}`);
  return r.result?.value;
}
await call('Runtime.enable');

const readModes=()=>evalJs(`(()=>{
  const find=name=>[...document.querySelectorAll('[aria-pressed]')].find(e=>String(e.innerText||'').trim()===name && e.getBoundingClientRect().width>0);
  const d=find('DeepThink'), s=find('Search');
  return {
    href:String(location.href||''),
    deepthinkFound:!!d,
    searchFound:!!s,
    deepthink:d?d.getAttribute('aria-pressed'):null,
    search:s?s.getAttribute('aria-pressed'):null
  };
})()`);

let before=await readModes();
console.log(`BEFORE_DEEPTHINK=${before.deepthink}`);
console.log(`BEFORE_SEARCH=${before.search}`);
if(!before.deepthinkFound) throw new Error('DEEPTHINK_TOGGLE_NOT_FOUND');
if(!before.searchFound) throw new Error('SEARCH_TOGGLE_NOT_FOUND');

if(before.search==='true'){
  const ok=await evalJs(`(()=>{const e=[...document.querySelectorAll('[aria-pressed]')].find(x=>String(x.innerText||'').trim()==='Search'&&x.getBoundingClientRect().width>0);if(!e)return false;e.click();return true})()`);
  if(!ok) throw new Error('SEARCH_TOGGLE_CLICK_FAILED');
  await sleep(700);
}

let mid=await readModes();
if(mid.deepthink!=='true'){
  const ok=await evalJs(`(()=>{const e=[...document.querySelectorAll('[aria-pressed]')].find(x=>String(x.innerText||'').trim()==='DeepThink'&&x.getBoundingClientRect().width>0);if(!e)return false;e.click();return true})()`);
  if(!ok) throw new Error('DEEPTHINK_TOGGLE_CLICK_FAILED');
  await sleep(900);
}

const after=await readModes();
const pass=after.deepthink==='true'&&after.search==='false';
console.log(`AFTER_DEEPTHINK=${after.deepthink}`);
console.log(`AFTER_SEARCH=${after.search}`);
console.log(`DEEPSEEK_DEEPTHINK_READY=${pass?'true':'false'}`);
ws.close();
if(!pass) process.exit(2);
