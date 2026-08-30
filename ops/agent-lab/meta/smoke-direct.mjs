import crypto from 'node:crypto';

const CDP=process.env.META_LAB_CDP_URL||'http://127.0.0.1:9232';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const nonce=crypto.randomBytes(4).toString('hex').toUpperCase();
const expected=`META_SMOKE_OK:${nonce}`;
const prompt=`HIVE Meta AI smoke test ${nonce}. Rispondi ESATTAMENTE e senza altro testo: ${expected}`;

async function json(url,opts={}){const r=await fetch(url,opts);if(!r.ok)throw new Error(`HTTP_${r.status}_${url}`);return r.json();}
let targets=await json(`${CDP}/json/list`);
let target=targets.find(t=>t.type==='page'&&/meta\.ai/i.test(t.url||''));
if(!target){target=await json(`${CDP}/json/new?${encodeURIComponent('https://www.meta.ai/')}`,{method:'PUT'});await sleep(2500);}
if(!target?.webSocketDebuggerUrl)throw new Error('META_PAGE_NOT_FOUND');

const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});});
let seq=0;const pending=new Map();
ws.addEventListener('message',ev=>{let m;try{m=JSON.parse(ev.data);}catch{return;}if(!m.id||!pending.has(m.id))return;const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(new Error(`CDP_${m.error.code}:${m.error.message}`)):p.resolve(m.result||{});});
function call(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evalJs(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}`);return r.result?.value;}
await call('Runtime.enable');await call('Page.enable').catch(()=>{});

const start=Date.now();let state={};
while(Date.now()-start<45000){
  state=await evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const input=[...document.querySelectorAll('input,textarea,[contenteditable="true"]')].filter(visible).find(e=>/ask meta ai/i.test(String(e.getAttribute('aria-label')||e.getAttribute('placeholder')||'')));const send=[...document.querySelectorAll('button,[role="button"]')].filter(visible).find(e=>/^send$/i.test(String(e.getAttribute('aria-label')||e.innerText||'').trim()));return {href:String(location.href||''),ready:document.readyState,input:!!input,send:!!send,body:String(document.body?.innerText||'')};})()`);
  if(state.input&&state.ready!=='loading')break;
  await sleep(500);
}
if(!state.input)throw new Error(`META_COMPOSER_NOT_READY href=${state.href||''}`);

const count=(s,t)=>t?s.split(t).length-1:0;
const before=count(state.body,expected);
const focused=await evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const e=[...document.querySelectorAll('input,textarea,[contenteditable="true"]')].filter(visible).find(x=>/ask meta ai/i.test(String(x.getAttribute('aria-label')||x.getAttribute('placeholder')||'')));if(!e)return false;e.focus();return true;})()`);
if(!focused)throw new Error('META_COMPOSER_NOT_FOUND');
await call('Input.dispatchKeyEvent',{type:'rawKeyDown',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
await call('Input.dispatchKeyEvent',{type:'keyUp',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
await call('Input.insertText',{text:prompt});
await sleep(500);
const inserted=await evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const e=[...document.querySelectorAll('input,textarea,[contenteditable="true"]')].filter(visible).find(x=>/ask meta ai/i.test(String(x.getAttribute('aria-label')||x.getAttribute('placeholder')||'')));return e?String(e.value||e.innerText||e.textContent||''):'';})()`);
if(!inserted.includes(nonce))throw new Error('META_TEXT_NOT_INSERTED');

const sendReady=await evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const e=[...document.querySelectorAll('button,[role="button"]')].filter(visible).find(x=>/^send$/i.test(String(x.getAttribute('aria-label')||x.innerText||'').trim()));return !!e&&!e.disabled;})()`);
let method='ENTER';
if(sendReady){
  const clicked=await evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const e=[...document.querySelectorAll('button,[role="button"]')].filter(visible).find(x=>/^send$/i.test(String(x.getAttribute('aria-label')||x.innerText||'').trim()));if(!e||e.disabled)return false;e.click();return true;})()`);
  if(clicked)method='SEND_BUTTON';
}
if(method==='ENTER'){
  await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
}
console.log('META_SMOKE_SENT=true');
console.log(`NONCE=${nonce}`);
console.log(`SUBMIT_METHOD=${method}`);

let captured=false,actual='',body='';const waitStart=Date.now();let stable=0,last=-1;
while(Date.now()-waitStart<120000){
  body=await evalJs(`String(document.body?.innerText||'')`).catch(()=> '');
  const n=count(body,expected);
  if(n>=before+2){if(n===last)stable++;else stable=0;last=n;if(stable>=2){captured=true;actual=expected;break;}}
  const gate=await evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const dialogs=[...document.querySelectorAll('[role="dialog"],[aria-modal="true"]')].filter(visible).map(e=>String(e.innerText||''));return dialogs.some(t=>/log in|sign up|continue with facebook|continue with instagram|continue with email/i.test(t));})()`).catch(()=>false);
  if(gate){console.log('META_SMOKE_BLOCKED_BY_LOGIN=true');console.log(`BODY_TAIL=${JSON.stringify(body.slice(-5000))}`);ws.close();process.exit(3);}
  await sleep(750);
}
console.log(`META_SMOKE_CAPTURE=${captured?'true':'false'}`);
console.log(`EXPECTED=${expected}`);
console.log(`ACTUAL=${actual}`);
console.log(`META_SMOKE_PASS=${captured&&actual===expected?'true':'false'}`);
if(!captured)console.log(`BODY_TAIL=${JSON.stringify(body.slice(-7000))}`);
ws.close();
if(!(captured&&actual===expected))process.exit(2);
