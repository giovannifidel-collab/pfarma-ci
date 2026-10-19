const CDP=process.env.DUCK_LAB_CDP_URL||'http://127.0.0.1:9233';
async function json(url){const r=await fetch(url);if(!r.ok)throw new Error(`HTTP_${r.status}_${url}`);return r.json();}
const targets=await json(`${CDP}/json/list`);
const target=targets.find(t=>t.type==='page'&&/duck\.ai/i.test(t.url||''));
if(!target?.webSocketDebuggerUrl)throw new Error('DUCK_PAGE_NOT_FOUND');
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('CDP_CONNECT_TIMEOUT')),15000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('CDP_CONNECT_ERROR'));},{once:true});});
let seq=0;const pending=new Map();
ws.addEventListener('message',ev=>{let m;try{m=JSON.parse(ev.data);}catch{return;}if(!m.id||!pending.has(m.id))return;const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(new Error(m.error.message)):p.resolve(m.result||{});});
function call(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evalJs(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.text||'EVAL_EXCEPTION');return r.result?.value;}
await call('Runtime.enable');
const marker='HIVE_DUCK_SUBMIT_PROBE_'+Date.now().toString(16).toUpperCase();
const markerLit=JSON.stringify(marker);
const info=await evalJs(`(()=>{
  const marker=${markerLit};
  const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
  const controls=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);
  const composer=controls.find(e=>/ask anything privately/i.test(String(e.getAttribute('placeholder')||e.getAttribute('aria-label')||'')))||controls.find(e=>e.tagName==='TEXTAREA')||null;
  if(!composer)return {error:'NO_COMPOSER'};
  composer.focus();
  const proto=Object.getPrototypeOf(composer);
  const desc=Object.getOwnPropertyDescriptor(proto,'value');
  if(desc?.set) desc.set.call(composer,marker); else composer.value=marker;
  composer.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:marker}));
  composer.dispatchEvent(new Event('change',{bubbles:true}));
  const form=composer.closest('form');
  const buttons=[...document.querySelectorAll('button,[role="button"],input[type="submit"]')].filter(visible).map((e,i)=>({i,tag:e.tagName.toLowerCase(),type:e.getAttribute('type'),text:String(e.innerText||e.value||'').trim().slice(0,120),aria:e.getAttribute('aria-label'),title:e.getAttribute('title'),disabled:!!e.disabled,ariaDisabled:e.getAttribute('aria-disabled'),formAction:e.getAttribute('formaction'),classes:String(e.className||'').slice(0,180)}));
  const formButtons=form?[...form.querySelectorAll('button,[role="button"],input[type="submit"]')].map((e,i)=>({i,tag:e.tagName.toLowerCase(),type:e.getAttribute('type'),text:String(e.innerText||e.value||'').trim().slice(0,120),aria:e.getAttribute('aria-label'),disabled:!!e.disabled,ariaDisabled:e.getAttribute('aria-disabled')})):[];
  const parentHTML=composer.parentElement?.parentElement?.outerHTML?.slice(0,8000)||'';
  return {href:location.href,marker,composerTag:composer.tagName.toLowerCase(),composerValue:String(composer.value||composer.innerText||composer.textContent||''),formPresent:!!form,formAction:form?.getAttribute('action')||null,formMethod:form?.getAttribute('method')||null,buttons,formButtons,parentHTML};
})()`);
console.log('=== DUCK SUBMIT STATE PROBE ===');
if(info.error)console.log(`ERROR=${info.error}`);
console.log(`URL=${info.href||''}`);
console.log(`MARKER=${info.marker||marker}`);
console.log(`COMPOSER_TAG=${info.composerTag||''}`);
console.log(`COMPOSER_VALUE=${JSON.stringify(info.composerValue||'')}`);
console.log(`FORM_PRESENT=${info.formPresent?'true':'false'}`);
console.log(`FORM_ACTION=${info.formAction||''}`);
console.log(`FORM_METHOD=${info.formMethod||''}`);
console.log(`FORM_BUTTONS=${JSON.stringify(info.formButtons||[],null,2)}`);
console.log(`ALL_BUTTONS=${JSON.stringify(info.buttons||[],null,2)}`);
console.log(`COMPOSER_PARENT_HTML=${JSON.stringify(info.parentHTML||'')}`);
ws.close();
