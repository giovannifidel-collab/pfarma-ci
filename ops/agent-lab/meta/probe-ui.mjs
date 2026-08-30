const CDP=process.env.META_LAB_CDP_URL||'http://127.0.0.1:9232';
async function json(url){const r=await fetch(url);if(!r.ok)throw new Error(`HTTP_${r.status}_${url}`);return r.json();}
const targets=await json(`${CDP}/json/list`);
const target=targets.find(t=>t.type==='page'&&/meta\.ai/i.test(t.url||''));
if(!target?.webSocketDebuggerUrl)throw new Error('META_PAGE_NOT_FOUND');
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});});
let seq=0;const pending=new Map();
ws.addEventListener('message',ev=>{let m;try{m=JSON.parse(ev.data);}catch{return;}if(!m.id||!pending.has(m.id))return;const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(new Error(`CDP_${m.error.code}:${m.error.message}`)):p.resolve(m.result||{});});
function call(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evalJs(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}`);return r.result?.value;}
await call('Runtime.enable');
const info=await evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const controls=[...document.querySelectorAll('textarea,[contenteditable="true"],input')].filter(visible).slice(0,20).map(e=>({tag:e.tagName.toLowerCase(),type:e.getAttribute('type'),placeholder:e.getAttribute('placeholder'),aria:e.getAttribute('aria-label'),contenteditable:e.getAttribute('contenteditable'),role:e.getAttribute('role')}));const buttons=[...document.querySelectorAll('button,a,[role="button"]')].filter(visible).slice(0,50).map(e=>({tag:e.tagName.toLowerCase(),text:String(e.innerText||'').trim().slice(0,120),aria:e.getAttribute('aria-label'),title:e.getAttribute('title'),pressed:e.getAttribute('aria-pressed')}));const dialogs=[...document.querySelectorAll('[role="dialog"],[aria-modal="true"]')].filter(visible).map(e=>String(e.innerText||'').trim().slice(0,1000));const body=String(document.body?.innerText||'');const login=/log in|login|sign in|continue with facebook|continue with instagram/i.test(body);const chat=controls.some(c=>c.tag==='textarea'||c.contenteditable==='true')||/ask meta ai|message meta ai|what can i help/i.test(body);const modes=[...document.querySelectorAll('*')].filter(visible).map(e=>String(e.innerText||'').trim()).filter(t=>/^(thinking|think|reasoning|search|web)$/i.test(t)).slice(0,30);return {url:location.href,title:document.title,ready:document.readyState,loginHint:login,chatHint:chat,controls,buttons,dialogs,modes,bodyTail:body.slice(-3500)};})()`);
console.log('=== META AI UI PROBE ===');
console.log(`URL=${info.url}`);
console.log(`TITLE=${info.title}`);
console.log(`READY_STATE=${info.ready}`);
console.log(`LOGIN_HINT=${info.loginHint}`);
console.log(`CHAT_HINT=${info.chatHint}`);
console.log(`CONTROLS=${JSON.stringify(info.controls,null,2)}`);
console.log(`BUTTONS=${JSON.stringify(info.buttons,null,2)}`);
console.log(`DIALOGS=${JSON.stringify(info.dialogs,null,2)}`);
console.log(`MODE_TEXT=${JSON.stringify(info.modes,null,2)}`);
console.log(`BODY_TAIL=${JSON.stringify(info.bodyTail)}`);
ws.close();
