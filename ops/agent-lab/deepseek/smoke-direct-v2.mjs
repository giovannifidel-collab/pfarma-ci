import crypto from 'node:crypto';

const CDP=process.env.DEEPSEEK_LAB_CDP_URL||'http://127.0.0.1:9227';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const nonce=crypto.randomBytes(4).toString('hex').toUpperCase();
const expected=`DEEPSEEK_SMOKE_OK:${nonce}`;

async function json(url,opts={}){
  const r=await fetch(url,opts);
  if(!r.ok) throw new Error(`HTTP_${r.status}_${url}`);
  return r.json();
}

let targets=await json(`${CDP}/json/list`);
let target=targets.find(t=>t.type==='page'&&/chat\.deepseek\.com/i.test(t.url||'')&&!/sign_in/i.test(t.url||''));
if(!target) target=targets.find(t=>t.type==='page'&&/chat\.deepseek\.com/i.test(t.url||''));
if(!target){
  target=await json(`${CDP}/json/new?${encodeURIComponent('https://chat.deepseek.com/')}`,{method:'PUT'});
  await sleep(2500);
}
if(!target?.webSocketDebuggerUrl) throw new Error('NO_DEEPSEEK_PAGE_WEBSOCKET');

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
  if(!msg.id||!pending.has(msg.id)) return;
  const p=pending.get(msg.id); pending.delete(msg.id); clearTimeout(p.timer);
  if(msg.error) p.reject(new Error(`CDP_${msg.error.code}:${msg.error.message}`));
  else p.resolve(msg.result||{});
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
  if(r.exceptionDetails){
    const d=r.exceptionDetails;
    throw new Error(`EVAL_EXCEPTION_${d.text||'unknown'}_${d.exception?.description||''}`);
  }
  return r.result?.value;
}
await call('Runtime.enable');
await call('Page.enable').catch(()=>{});

const start=Date.now();
let state=null;
while(Date.now()-start<45000){
  state=await evalJs(`(()=>{
    const body=String(document.body?.innerText||'');
    const href=String(location.href||'');
    const ta=[...document.querySelectorAll('textarea')].find(e=>{
      const r=e.getBoundingClientRect();
      const s=getComputedStyle(e);
      return String(e.getAttribute('placeholder')||'').toLowerCase().includes('message deepseek') && r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden';
    });
    const low=body.toLowerCase();
    const login=href.includes('/sign_in') || low.includes('phone number / email address');
    return {href,ready:document.readyState,login,textarea:!!ta,body};
  })()`);
  if(state?.login) throw new Error('DEEPSEEK_LOGIN_REQUIRED');
  if(state?.textarea&&state.ready!=='loading') break;
  await sleep(500);
}
if(!state?.textarea) throw new Error(`DEEPSEEK_COMPOSER_NOT_READY href=${state?.href||''}`);

const esc=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
const tokenRe=new RegExp(esc(expected),'g');
const before=(state.body.match(tokenRe)||[]).length;
const prompt=`HIVE DeepSeek smoke test ${nonce}. Rispondi ESATTAMENTE e senza altro testo: ${expected}`;

const focused=await evalJs(`(()=>{
  const e=[...document.querySelectorAll('textarea')].find(x=>String(x.getAttribute('placeholder')||'').toLowerCase().includes('message deepseek')&&x.getBoundingClientRect().width>0);
  if(!e) return false;
  e.focus();
  return true;
})()`);
if(!focused) throw new Error('DEEPSEEK_COMPOSER_NOT_FOUND');

await call('Input.dispatchKeyEvent',{type:'rawKeyDown',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
await call('Input.dispatchKeyEvent',{type:'keyUp',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
await call('Input.insertText',{text:prompt});
await sleep(400);

const composer=await evalJs(`(()=>{const e=[...document.querySelectorAll('textarea')].find(x=>String(x.getAttribute('placeholder')||'').toLowerCase().includes('message deepseek')&&x.getBoundingClientRect().width>0);return e?String(e.value||''):''})()`);
if(!composer.includes(expected)) throw new Error(`DEEPSEEK_TEXT_NOT_INSERTED len=${composer.length}`);

await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
console.log('DEEPSEEK_SMOKE_SENT=true');
console.log(`NONCE=${nonce}`);

const waitStart=Date.now();
let body='';
while(Date.now()-waitStart<90000){
  body=await evalJs(`String(document.body?.innerText||'')`).catch(()=> '');
  const count=(body.match(tokenRe)||[]).length;
  if(count>=before+2){
    console.log('DEEPSEEK_SMOKE_CAPTURE=true');
    console.log(`EXPECTED=${expected}`);
    console.log(`ACTUAL=${expected}`);
    console.log('DEEPSEEK_SMOKE_PASS=true');
    ws.close();
    process.exit(0);
  }
  await sleep(600);
}

console.log('DEEPSEEK_SMOKE_CAPTURE=false');
console.log(`BODY_TAIL=${JSON.stringify(body.slice(-8000))}`);
ws.close();
process.exit(2);
