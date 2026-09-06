const CDP=process.env.COPILOT_LAB_CDP_URL||'http://127.0.0.1:9231';
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
async function evalJs(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}`);return r.result?.value;}
await call('Runtime.enable');
const expression=`(()=>{
 const visible=e=>{try{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&Number(s.opacity||1)>0}catch{return false}};
 const text=e=>String(e.innerText||e.textContent||'').replace(/\\s+/g,' ').trim();
 const attrs=e=>({tag:e.tagName?.toLowerCase()||'',text:text(e).slice(0,180),aria:e.getAttribute?.('aria-label'),title:e.getAttribute?.('title'),pressed:e.getAttribute?.('aria-pressed'),expanded:e.getAttribute?.('aria-expanded'),role:e.getAttribute?.('role'),visible:visible(e)});
 const composer=[...document.querySelectorAll('[contenteditable="true"],textarea')].find(visible)||null;
 if(composer){try{composer.focus()}catch{}}
 const all=[...document.querySelectorAll('button,[role="button"],a,[aria-label],[title],[role="menuitem"],[role="option"]')];
 const re=/think deeper|deep think|reason|study and learn|study|search|quick response|smart|mode|model/i;
 const candidates=all.filter(e=>re.test([text(e),e.getAttribute?.('aria-label'),e.getAttribute?.('title')].filter(Boolean).join(' '))).map(attrs).slice(0,120);
 const hiddenText=[...document.querySelectorAll('*')].filter(e=>re.test(text(e))&&text(e).length<120).map(attrs).slice(0,120);
 return {url:location.href,title:document.title,composer:composer?attrs(composer):null,candidates,hiddenText};
})()`;
await sleep(700);
const info=await evalJs(expression);
console.log('=== COPILOT MODE PROBE ===');
console.log(`URL=${info.url||''}`);
console.log(`TITLE=${info.title||''}`);
console.log(`COMPOSER=${JSON.stringify(info.composer)}`);
console.log(`CANDIDATES=${JSON.stringify(info.candidates,null,2)}`);
console.log(`MODE_TEXT_NODES=${JSON.stringify(info.hiddenText,null,2)}`);
console.log(`THINK_DEEPER_DISCOVERED=${JSON.stringify([...(info.candidates||[]),...(info.hiddenText||[])].some(x=>/think deeper|deep think/i.test(`${x.text||''} ${x.aria||''} ${x.title||''}`)))}`);
ws.close();
