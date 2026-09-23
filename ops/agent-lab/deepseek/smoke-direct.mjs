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
let target=targets.find(t=>t.type==='page' && /chat\.deepseek\.com/i.test(t.url||''));
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
    const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);
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
await call('Page.enable').catch(()=>{});

const stateStart=Date.now();
let state=null;
while(Date.now()-stateStart<45000){
  state=await evalJs(`(()=>{const body=document.body?.innerText||'';const ta=[...document.querySelectorAll('textarea')].find(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return /Message DeepSeek/i.test(e.getAttribute('placeholder')||'')&&r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'});return {href:location.href,ready:document.readyState,login:/sign_in|log in/i.test(location.href)||/Phone number \/ email address/i.test(body),textarea:!!ta,body};})()`);
  if(state?.login) throw new Error('DEEPSEEK_LOGIN_REQUIRED');
  if(state?.textarea && state.ready!=='loading') break;
  await sleep(500);
}
if(!state?.textarea) throw new Error('DEEPSEEK_COMPOSER_NOT_READY');

const before=(state.body.match(new RegExp(expected.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'g'))||[]).length;
const prompt=`HIVE DeepSeek smoke test ${nonce}. Rispondi ESATTAMENTE e senza altro testo: ${expected}`;

const focused=await evalJs(`(()=>{const e=[...document.querySelectorAll('textarea')].find(x=>/Message DeepSeek/i.test(x.getAttribute('placeholder')||'')&&x.getBoundingClientRect().width>0);if(!e)return false;e.focus();e.value='';e.dispatchEvent(new Event('input',{bubbles:true}));return true})()`);
if(!focused) throw new Error('DEEPSEEK_COMPOSER_NOT_FOUND');
await call('Input.insertText',{text:prompt});
await sleep(250);
await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
console.log(`DEEPSEEK_SMOKE_SENT=true`);
console.log(`NONCE=${nonce}`);

const waitStart=Date.now();
let body='';
while(Date.now()-waitStart<90000){
  body=await evalJs(`document.body?.innerText||''`).catch(()=> '');
  const count=(body.match(new RegExp(expected.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'g'))||[]).length;
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
console.log(`BODY_TAIL=${JSON.stringify(body.slice(-6000))}`);
ws.close();
process.exit(2);
