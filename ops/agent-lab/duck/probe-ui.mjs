const CDP=process.env.DUCK_LAB_CDP_URL||'http://127.0.0.1:9233';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function json(url){const r=await fetch(url);if(!r.ok)throw new Error(`HTTP_${r.status}_${url}`);return r.json();}
let targets=await json(`${CDP}/json/list`);
let target=targets.find(t=>t.type==='page'&&/duck\.ai|duckduckgo\.com/i.test(t.url||''));
if(!target){target=await json(`${CDP}/json/new?${encodeURIComponent('https://duck.ai/')}`,{method:'PUT'});await sleep(1800);}
if(!target?.webSocketDebuggerUrl)throw new Error('DUCK_PAGE_NOT_FOUND');
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});});
let seq=0;const pending=new Map();const events=[];
ws.addEventListener('message',ev=>{let m;try{m=JSON.parse(ev.data);}catch{return;}if(m.method==='Runtime.consoleAPICalled'){events.push({type:'console',level:m.params?.type,args:(m.params?.args||[]).map(x=>x.value??x.description).filter(Boolean).slice(0,6)});return;}if(m.method==='Log.entryAdded'){events.push({type:'log',level:m.params?.entry?.level,text:m.params?.entry?.text?.slice(0,800),url:m.params?.entry?.url});return;}if(!m.id||!pending.has(m.id))return;const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(new Error(`CDP_${m.error.code}:${m.error.message}`)):p.resolve(m.result||{});});
function call(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evalJs(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}`);return r.result?.value;}
await call('Runtime.enable');await call('Page.enable').catch(()=>{});await call('Log.enable').catch(()=>{});
let href=await evalJs(`String(location.href||'')`);
if(href==='about:blank'){
  console.log('DUCK_NAV_RECOVERY_FROM=about:blank');
  await call('Page.navigate',{url:'https://duck.ai/'});
  const start=Date.now();
  while(Date.now()-start<30000){await sleep(500);href=await evalJs(`String(location.href||'')`).catch(()=> '');const ready=await evalJs(`document.readyState`).catch(()=> 'loading');if(href!=='about:blank'&&ready!=='loading')break;}
  console.log(`DUCK_NAV_RECOVERY_TO=${href}`);
}
async function snapshot(){return evalJs(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const controls=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible).slice(0,30).map(e=>({tag:e.tagName.toLowerCase(),type:e.getAttribute('type'),placeholder:e.getAttribute('placeholder'),aria:e.getAttribute('aria-label'),role:e.getAttribute('role'),contenteditable:e.getAttribute('contenteditable')}));const buttons=[...document.querySelectorAll('button,a,[role="button"]')].filter(visible).slice(0,80).map(e=>({tag:e.tagName.toLowerCase(),text:String(e.innerText||'').trim().slice(0,140),aria:e.getAttribute('aria-label'),title:e.getAttribute('title'),pressed:e.getAttribute('aria-pressed')}));const dialogs=[...document.querySelectorAll('[role="dialog"],[aria-modal="true"]')].filter(visible).map(e=>String(e.innerText||'').trim().slice(0,1200));const body=String(document.body?.innerText||'');const composer=controls.some(c=>c.tag==='textarea'||c.contenteditable==='true'||c.role==='textbox');const consent=/agree|privacy|terms|continue|got it|accept/i.test(body);const login=/log in|sign in|create account/i.test(body);const modelTexts=[...document.querySelectorAll('button,[role="button"],div,span')].filter(visible).map(e=>String(e.innerText||'').trim()).filter(t=>/claude|mistral|gpt|gemma|oss|llama/i.test(t)&&t.length<120).slice(0,40);const scripts=[...document.scripts].map(s=>s.src||'[inline]').slice(0,40);const resources=performance.getEntriesByType('resource').map(r=>({name:r.name,kind:r.initiatorType,duration:Math.round(r.duration)})).slice(-40);return {url:location.href,title:document.title,ready:document.readyState,composer,consent,login,controls,buttons,dialogs,modelTexts,bodyTail:body.slice(-4500),bodyLength:body.length,htmlLength:document.documentElement?.outerHTML?.length||0,scriptCount:document.scripts.length,scripts,resources};})()`);}
let info=await snapshot();
const mountStart=Date.now();
while(Date.now()-mountStart<30000&&!info.composer&&info.bodyLength<80){await sleep(1000);info=await snapshot();}
if(!info.composer&&info.bodyLength<80){
  console.log('DUCK_SPA_MOUNT_TIMEOUT=true');
  console.log('DUCK_RELOAD_ATTEMPT=true');
  await call('Page.reload',{ignoreCache:true});
  await sleep(2500);
  const reloadStart=Date.now();
  while(Date.now()-reloadStart<30000){info=await snapshot().catch(()=>info);if(info.composer||info.bodyLength>=80)break;await sleep(1000);}
}
console.log('=== DUCK AI UI PROBE ===');
console.log(`URL=${info.url}`);
console.log(`TITLE=${info.title}`);
console.log(`READY_STATE=${info.ready}`);
console.log(`COMPOSER_HINT=${info.composer}`);
console.log(`CONSENT_HINT=${info.consent}`);
console.log(`LOGIN_HINT=${info.login}`);
console.log(`BODY_LENGTH=${info.bodyLength}`);
console.log(`HTML_LENGTH=${info.htmlLength}`);
console.log(`SCRIPT_COUNT=${info.scriptCount}`);
console.log(`CONTROLS=${JSON.stringify(info.controls,null,2)}`);
console.log(`BUTTONS=${JSON.stringify(info.buttons,null,2)}`);
console.log(`DIALOGS=${JSON.stringify(info.dialogs,null,2)}`);
console.log(`MODEL_TEXT=${JSON.stringify(info.modelTexts,null,2)}`);
console.log(`SCRIPTS=${JSON.stringify(info.scripts,null,2)}`);
console.log(`RESOURCE_TAIL=${JSON.stringify(info.resources,null,2)}`);
console.log(`PAGE_EVENTS=${JSON.stringify(events.slice(-30),null,2)}`);
console.log(`BODY_TAIL=${JSON.stringify(info.bodyTail)}`);
ws.close();
