import crypto from 'node:crypto';
const CDP=process.env.COPILOT_LAB_CDP_URL||'http://127.0.0.1:9231';
const nonce=crypto.randomBytes(4).toString('hex').toUpperCase();
const expected=`COPILOT_SMOKE_OK:${nonce}`;
const prompt=`HIVE Copilot smoke test ${nonce}. Rispondi ESATTAMENTE e senza altro testo: ${expected}`;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function json(url,opts={}){const r=await fetch(url,opts);if(!r.ok)throw new Error(`HTTP_${r.status}_${url}`);return r.json();}
let targets=await json(`${CDP}/json/list`);
let target=targets.find(t=>t.type==='page'&&/copilot\.(com|microsoft\.com)/i.test(t.url||''));
if(!target?.webSocketDebuggerUrl)throw new Error('COPILOT_PAGE_NOT_FOUND');
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});});
let seq=0;const pending=new Map();
ws.addEventListener('message',ev=>{let m;try{m=JSON.parse(ev.data);}catch{return;}if(!m.id||!pending.has(m.id))return;const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(new Error(`CDP_${m.error.code}:${m.error.message}`)):p.resolve(m.result||{});});
function call(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evalJs(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}_${r.exceptionDetails.exception?.description||''}`);return r.result?.value;}
await call('Runtime.enable');
const bodyText=()=>evalJs(`String(document.body?.innerText||'')`);
const count=(s,t)=>t?s.split(t).length-1:0;
const before=count(await bodyText(),expected);
const focused=await evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const all=[...document.querySelectorAll('[contenteditable="true"],textarea')].filter(visible);const e=all.find(x=>/message copilot/i.test(x.getAttribute('aria-label')||x.getAttribute('placeholder')||''))||all[0];if(!e)return false;e.focus();return true})()`);
if(!focused)throw new Error('COPILOT_COMPOSER_NOT_FOUND');
await call('Input.dispatchKeyEvent',{type:'rawKeyDown',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
await call('Input.dispatchKeyEvent',{type:'keyUp',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
await call('Input.insertText',{text:prompt});
await sleep(400);
const inserted=await evalJs(`(()=>{const a=document.activeElement;return String(a?.innerText||a?.value||a?.textContent||'')})()`);
if(!inserted.includes(nonce))throw new Error('COPILOT_TEXT_NOT_INSERTED');
await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
console.log('COPILOT_SMOKE_SENT=true');
console.log(`NONCE=${nonce}`);
let captured=false,actual='';let stable=0,lastCount=-1;
const start=Date.now();
while(Date.now()-start<180000){
  const b=await bodyText();
  const n=count(b,expected);
  if(n>=before+2){
    if(n===lastCount)stable++;else stable=0;
    lastCount=n;
    if(stable>=2){captured=true;actual=expected;break;}
  }
  const low=b.toLowerCase();
  if(/sign in|log in/.test(low)&&!/giovanni/i.test(low)&&!/message copilot/i.test(low))throw new Error('COPILOT_LOGIN_BLOCKED_DURING_SMOKE');
  await sleep(900);
}
console.log(`COPILOT_SMOKE_CAPTURE=${captured?'true':'false'}`);
console.log(`EXPECTED=${expected}`);
console.log(`ACTUAL=${actual}`);
console.log(`COPILOT_SMOKE_PASS=${captured&&actual===expected?'true':'false'}`);
ws.close();
if(!(captured&&actual===expected))process.exit(2);
