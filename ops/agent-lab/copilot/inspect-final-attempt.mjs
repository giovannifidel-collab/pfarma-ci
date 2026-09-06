const CDP=process.env.COPILOT_LAB_CDP_URL||'http://127.0.0.1:9231';
const NONCE=process.env.COPILOT_INSPECT_NONCE||'C1DA2526';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function json(url,opts={}){const r=await fetch(url,opts);if(!r.ok)throw new Error(`HTTP_${r.status}_${url}`);return r.json();}
const targets=await json(`${CDP}/json/list`);
const target=targets.find(t=>t.type==='page'&&/copilot\.(com|microsoft\.com)/i.test(t.url||''));
if(!target?.webSocketDebuggerUrl)throw new Error('COPILOT_PAGE_NOT_FOUND');
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});});
let seq=0;const pending=new Map();
ws.addEventListener('message',ev=>{let m;try{m=JSON.parse(ev.data);}catch{return;}if(!m.id||!pending.has(m.id))return;const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(new Error(`CDP_${m.error.code}:${m.error.message}`)):p.resolve(m.result||{});});
function call(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evalJs(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}_${r.exceptionDetails.exception?.description||''}`);return r.result?.value;}
await call('Runtime.enable');
await sleep(500);
const snapshot=await evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const body=String(document.body?.innerText||'');const composer=[...document.querySelectorAll('[contenteditable="true"],textarea')].filter(visible).find(x=>/message copilot/i.test(x.getAttribute('aria-label')||x.getAttribute('placeholder')||''));const controls=[...document.querySelectorAll('button,[role="button"]')].filter(visible).map(e=>({text:String(e.innerText||'').trim().slice(0,120),aria:e.getAttribute('aria-label'),disabled:!!e.disabled})).filter(x=>/send|stop|cancel|retry|regenerate|try again/i.test(String(x.aria||x.text||'')));const nodes=[...document.querySelectorAll('main,section,article,div,[role="article"]')].filter(visible).map(e=>String(e.innerText||'').trim()).filter(t=>t.includes(${JSON.stringify(NONCE)}));return {url:location.href,title:document.title,body,composerText:String(composer?.innerText||composer?.value||composer?.textContent||''),controls,nodes:nodes.slice(-30)};})()`);
const clean=s=>String(s||'').replace(/[\u200B-\u200D\u2060\uFEFF]/g,'');
const body=clean(snapshot.body);
const exactRe=new RegExp(`COPILOT_CERT_RESULT:${NONCE}:(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+)`,'g');
const tolerantRe=new RegExp(`COPILOT_CERT_RESULT\\s*:?\\s*${NONCE}[\\s:,-]*(\\d+)[\\s:,-]+(\\d+)[\\s:,-]+(\\d+)[\\s:,-]+(\\d+)[\\s:,-]+(\\d+)[\\s:,-]+(\\d+)[\\s:,-]+(\\d+)[\\s:,-]+(\\d+)[\\s:,-]+(\\d+)[\\s:,-]+(\\d+)[\\s:,-]+(\\d+)`,'gi');
const exact=[...body.matchAll(exactRe)].map(m=>m[0]);
const tolerant=[...body.matchAll(tolerantRe)].map(m=>({raw:m[0],values:m.slice(1).map(Number)}));
const idx=body.lastIndexOf(NONCE);
const context=idx>=0?body.slice(Math.max(0,idx-5000),Math.min(body.length,idx+9000)):body.slice(-12000);
console.log('=== COPILOT FINAL ATTEMPT INSPECTOR ===');
console.log(`NONCE=${NONCE}`);
console.log(`URL=${snapshot.url}`);
console.log(`TITLE=${snapshot.title}`);
console.log(`BODY_LENGTH=${body.length}`);
console.log(`NONCE_OCCURRENCES=${body.split(NONCE).length-1}`);
console.log(`EXACT_FINAL_MATCHES=${JSON.stringify(exact,null,2)}`);
console.log(`TOLERANT_FINAL_MATCHES=${JSON.stringify(tolerant,null,2)}`);
console.log(`COMPOSER_TEXT=${JSON.stringify(clean(snapshot.composerText))}`);
console.log(`ACTIVE_CONTROLS=${JSON.stringify(snapshot.controls,null,2)}`);
console.log(`NONCE_NODES=${JSON.stringify((snapshot.nodes||[]).map(clean),null,2)}`);
console.log('--- NONCE_CONTEXT ---');
console.log(context);
console.log('--- END_NONCE_CONTEXT ---');
ws.close();
