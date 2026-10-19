import crypto from 'node:crypto';

const CDP=process.env.MISTRAL_LAB_CDP_URL||'http://127.0.0.1:9229';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const nonce=crypto.randomBytes(4).toString('hex').toUpperCase();
const expected=`MISTRAL_SMOKE_OK:${nonce}`;

async function json(url,opts={}){const r=await fetch(url,opts);if(!r.ok)throw new Error(`HTTP_${r.status}_${url}`);return r.json();}
let targets=await json(`${CDP}/json/list`);
let target=targets.find(t=>t.type==='page'&&/chat\.mistral\.ai/i.test(t.url||''));
if(!target)throw new Error('MISTRAL_PAGE_NOT_FOUND');
if(!target.webSocketDebuggerUrl)throw new Error('NO_MISTRAL_PAGE_WEBSOCKET');

const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});});
let seq=0;const pending=new Map();
ws.addEventListener('message',ev=>{let msg;try{msg=JSON.parse(ev.data);}catch{return;}if(!msg.id||!pending.has(msg.id))return;const p=pending.get(msg.id);pending.delete(msg.id);clearTimeout(p.timer);if(msg.error)p.reject(new Error(`CDP_${msg.error.code}:${msg.error.message}`));else p.resolve(msg.result||{});});
function call(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evalJs(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}_${r.exceptionDetails.exception?.description||''}`);return r.result?.value;}
await call('Runtime.enable');await call('Page.enable').catch(()=>{});

async function bodyText(){return evalJs(`String(document.body?.innerText||'')`).catch(()=> '');}
function literalCount(text,token){return token?text.split(token).length-1:0;}

async function findComposer(){
  return evalJs(`(()=>{
    const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
    const all=[...document.querySelectorAll('[contenteditable="true"],textarea')].filter(visible);
    const e=all.find(x=>x.getAttribute('contenteditable')==='true')||all[all.length-1];
    if(!e)return null;
    return {tag:e.tagName.toLowerCase(),contenteditable:e.getAttribute('contenteditable'),text:String(e.innerText||e.value||'')};
  })()`);
}

const start=Date.now();let composer=null;
while(Date.now()-start<45000){composer=await findComposer();if(composer)break;await sleep(500);}
if(!composer)throw new Error('MISTRAL_COMPOSER_NOT_READY');

const before=literalCount(await bodyText(),expected);
const prompt=`HIVE Mistral smoke test ${nonce}. Rispondi ESATTAMENTE e senza altro testo: ${expected}`;

const focused=await evalJs(`(()=>{
  const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
  const all=[...document.querySelectorAll('[contenteditable="true"],textarea')].filter(visible);
  const e=all.find(x=>x.getAttribute('contenteditable')==='true')||all[all.length-1];
  if(!e)return false;e.focus();return true;
})()`);
if(!focused)throw new Error('MISTRAL_COMPOSER_NOT_FOUND');

await call('Input.dispatchKeyEvent',{type:'rawKeyDown',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
await call('Input.dispatchKeyEvent',{type:'keyUp',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
await call('Input.insertText',{text:prompt});
await sleep(400);

const inserted=await evalJs(`(()=>{
  const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
  const all=[...document.querySelectorAll('[contenteditable="true"],textarea')].filter(visible);
  const e=all.find(x=>x.getAttribute('contenteditable')==='true')||all[all.length-1];
  return e?String(e.innerText||e.value||''):'';
})()`);
if(!inserted.includes(expected))throw new Error(`MISTRAL_TEXT_NOT_INSERTED len=${inserted.length}`);

await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
console.log('MISTRAL_SMOKE_SENT=true');console.log(`NONCE=${nonce}`);

const waitStart=Date.now();let body='';
while(Date.now()-waitStart<120000){
  body=await bodyText();
  if(literalCount(body,expected)>=before+2){console.log('MISTRAL_SMOKE_CAPTURE=true');console.log(`EXPECTED=${expected}`);console.log(`ACTUAL=${expected}`);console.log('MISTRAL_SMOKE_PASS=true');ws.close();process.exit(0);}
  const low=body.toLowerCase();
  if(low.includes('sign in')&&low.includes('sign up')&&!low.includes('default workspace')){console.log('MISTRAL_SMOKE_BLOCKED_BY_LOGIN=true');console.log(`BODY_TAIL=${JSON.stringify(body.slice(-5000))}`);ws.close();process.exit(3);}
  await sleep(700);
}
console.log('MISTRAL_SMOKE_CAPTURE=false');console.log(`BODY_TAIL=${JSON.stringify(body.slice(-8000))}`);ws.close();process.exit(2);
