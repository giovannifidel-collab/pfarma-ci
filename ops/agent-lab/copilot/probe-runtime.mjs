const CDP=process.env.COPILOT_LAB_CDP_URL||'http://127.0.0.1:9231';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function json(url,opts={}){const r=await fetch(url,opts);if(!r.ok)throw new Error(`HTTP_${r.status}_${url}`);return r.json();}
let targets=await json(`${CDP}/json/list`);
let target=targets.find(t=>t.type==='page'&&/copilot\.microsoft\.com/i.test(t.url||''));
if(!target)throw new Error('COPILOT_PAGE_NOT_FOUND');
if(!target.webSocketDebuggerUrl)throw new Error('NO_COPILOT_PAGE_WEBSOCKET');
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});});
let seq=0;const pending=new Map();const events=[];
ws.addEventListener('message',ev=>{let msg;try{msg=JSON.parse(ev.data);}catch{return;}if(msg.id&&pending.has(msg.id)){const p=pending.get(msg.id);pending.delete(msg.id);clearTimeout(p.timer);if(msg.error)p.reject(new Error(`CDP_${msg.error.code}:${msg.error.message}`));else p.resolve(msg.result||{});return;}if(msg.method==='Runtime.exceptionThrown')events.push({type:'js-exception',text:msg.params?.exceptionDetails?.exception?.description||msg.params?.exceptionDetails?.text||'unknown'});if(msg.method==='Log.entryAdded')events.push({type:'log',level:msg.params?.entry?.level,text:msg.params?.entry?.text,source:msg.params?.entry?.source,url:msg.params?.entry?.url});if(msg.method==='Network.loadingFailed')events.push({type:'network-failed',url:msg.params?.requestId,errorText:msg.params?.errorText,canceled:msg.params?.canceled,blockedReason:msg.params?.blockedReason});});
function call(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evalJs(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}_${r.exceptionDetails.exception?.description||''}`);return r.result?.value;}
await call('Runtime.enable');await call('Log.enable').catch(()=>{});await call('Network.enable').catch(()=>{});await call('Page.enable').catch(()=>{});
await call('Page.reload',{ignoreCache:true}).catch(()=>{});
await sleep(8000);
const info=await evalJs(`(()=>{
  const de=document.documentElement;
  const b=document.body;
  const html=String(de?.outerHTML||'');
  const bodyHtml=String(b?.innerHTML||'');
  const scripts=[...document.scripts].map(s=>s.src||'[inline]').slice(0,60);
  const iframes=[...document.querySelectorAll('iframe')].map(f=>({src:f.src||null,title:f.title||null,name:f.name||null}));
  const children=[...b?.children||[]].map(e=>({tag:e.tagName,id:e.id||null,cls:String(e.className||'').slice(0,180),text:String(e.innerText||'').slice(0,300)})).slice(0,50);
  const resources=performance.getEntriesByType('resource').map(r=>({name:r.name,initiatorType:r.initiatorType,duration:Math.round(r.duration),transferSize:r.transferSize})).slice(-120);
  return {href:location.href,title:document.title,ready:document.readyState,htmlLength:html.length,bodyHtmlLength:bodyHtml.length,bodyTextLength:String(b?.innerText||'').length,children,iframes,scripts,resources,htmlTail:html.slice(-5000)};
})()`);
const frameTree=await call('Page.getFrameTree').catch(()=>({}));
console.log('=== COPILOT RUNTIME PROBE ===');
console.log(`URL=${info.href}`);console.log(`TITLE=${info.title}`);console.log(`READY_STATE=${info.ready}`);console.log(`HTML_LENGTH=${info.htmlLength}`);console.log(`BODY_HTML_LENGTH=${info.bodyHtmlLength}`);console.log(`BODY_TEXT_LENGTH=${info.bodyTextLength}`);console.log(`BODY_CHILDREN=${JSON.stringify(info.children,null,2)}`);console.log(`IFRAMES=${JSON.stringify(info.iframes,null,2)}`);console.log(`SCRIPTS=${JSON.stringify(info.scripts,null,2)}`);console.log(`FRAME_TREE=${JSON.stringify(frameTree.frameTree||{},null,2)}`);console.log(`EVENTS=${JSON.stringify(events.slice(-80),null,2)}`);console.log(`RESOURCES_TAIL=${JSON.stringify(info.resources.slice(-80),null,2)}`);console.log(`HTML_TAIL=${JSON.stringify(info.htmlTail)}`);
ws.close();
