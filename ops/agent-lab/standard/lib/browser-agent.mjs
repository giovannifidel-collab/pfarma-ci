import { spawnSync } from 'node:child_process';
import crypto from 'node:crypto';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const now = () => Date.now();
const safe = v => String(v ?? '');

async function fetchJson(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`HTTP_${r.status}_${url}`);
  return r.json();
}

async function portReady(port) {
  try {
    const r = await fetch(`http://127.0.0.1:${port}/json/version`, { signal: AbortSignal.timeout(1200) });
    return r.ok;
  } catch { return false; }
}

async function targetOnPort(port, targetPattern) {
  if (!await portReady(port)) return null;
  try {
    const list = await fetchJson(`http://127.0.0.1:${port}/json/list`);
    return list.find(t => t.type === 'page' && targetPattern.test(safe(t.url))) || null;
  } catch { return null; }
}

export class BrowserAgent {
  constructor(config, { rootDir, fresh = true } = {}) {
    this.config = config;
    this.id = config.id;
    this.rootDir = rootDir;
    this.fresh = fresh;
    this.port = config.port;
    this.ws = null;
    this.seq = 0;
    this.pending = new Map();
    this.lastHealth = null;
  }

  async discoverExistingPort() {
    const preferred = [this.config.port, ...(this.config.scanPorts || [])];
    const fallback = [];
    for (let p = 9222; p <= 9240; p++) if (!preferred.includes(p)) fallback.push(p);
    for (const p of [...preferred, ...fallback]) {
      const t = await targetOnPort(p, this.config.targetPattern);
      if (t) return { port: p, target: t };
    }
    return null;
  }

  async ensureBrowser() {
    let found = await this.discoverExistingPort();
    if (!found && this.config.startScript) {
      const script = `${this.rootDir}/${this.config.startScript}`;
      const r = spawnSync('bash', [script], { stdio:'inherit', cwd:this.rootDir, env:process.env });
      if (r.error) throw new Error(`START_BROWSER_ERROR:${r.error.message}`);
      if (r.status !== 0) throw new Error(`START_BROWSER_EXIT_${r.status}`);
      const deadline = now() + 30000;
      while (now() < deadline && !found) {
        found = await this.discoverExistingPort();
        if (!found) await sleep(500);
      }
    }
    if (!found) throw new Error('BROWSER_TARGET_NOT_FOUND');
    this.port = found.port;
    return found.target;
  }

  async connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    const target = await this.ensureBrowser();
    if (!target?.webSocketDebuggerUrl) throw new Error('PAGE_WEBSOCKET_NOT_FOUND');
    this.ws = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve,reject) => {
      const timer=setTimeout(()=>reject(new Error('CDP_CONNECT_TIMEOUT')),15000);
      this.ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});
      this.ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('CDP_CONNECT_ERROR'));},{once:true});
    });
    this.ws.addEventListener('message',ev=>{
      let m; try{m=JSON.parse(ev.data);}catch{return;}
      if(!m.id||!this.pending.has(m.id))return;
      const p=this.pending.get(m.id);this.pending.delete(m.id);clearTimeout(p.timer);
      if(m.error)p.reject(new Error(`CDP_${m.error.code}:${m.error.message}`));else p.resolve(m.result||{});
    });
    await this.call('Runtime.enable');
    await this.call('Page.enable').catch(()=>{});
  }

  call(method,params={},timeout=30000){
    const id=++this.seq;
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{this.pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},timeout);
      this.pending.set(id,{resolve,reject,timer});
      this.ws.send(JSON.stringify({id,method,params}));
    });
  }

  async eval(expression){
    const r=await this.call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION:${r.exceptionDetails.text||'unknown'}`);
    return r.result?.value;
  }

  async bodyText(){return this.eval(`String(document.body?.innerText||'')`).catch(()=> '');}
  patternsJs(list=[]){return JSON.stringify(list.map(String));}

  async uiState(){
    const cfg=this.config;
    return this.eval(`(()=>{
      const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const norm=e=>String(e?.getAttribute?.('aria-label')||e?.getAttribute?.('placeholder')||e?.innerText||e?.textContent||'').trim();
      const matches=(text,pats)=>pats.some(p=>{try{return new RegExp(p,'i').test(text)}catch{return false}});
      const cp=${this.patternsJs(cfg.composerPatterns)};
      const sp=${this.patternsJs(cfg.submitPatterns)};
      const xp=${this.patternsJs(cfg.stopPatterns||['^stop$','stop generating','stop responding','cancel response'])};
      const bp=${this.patternsJs(cfg.blockPatterns||[])};
      const controls=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);
      let composer=controls.find(e=>matches(norm(e),cp));
      if(!composer)composer=controls.find(e=>e.tagName==='TEXTAREA')||controls.find(e=>e.getAttribute('contenteditable')==='true')||controls.find(e=>e.getAttribute('role')==='textbox')||null;
      const actions=[...document.querySelectorAll('button,[role="button"],input[type="submit"]')].filter(visible);
      let submit=actions.find(e=>matches(norm(e),sp)&&!e.disabled&&e.getAttribute('aria-disabled')!=='true');
      if(!submit)submit=actions.find(e=>e.getAttribute('type')==='submit'&&!e.disabled&&e.getAttribute('aria-disabled')!=='true')||null;
      const stop=actions.find(e=>matches(norm(e),xp)&&!e.disabled&&e.getAttribute('aria-disabled')!=='true')||null;
      const body=String(document.body?.innerText||'');
      const block=bp.find(p=>{try{return new RegExp(p,'i').test(body)}catch{return false}})||null;
      const text=composer?String(composer.value||composer.innerText||composer.textContent||''):'';
      return {href:String(location.href||''),title:document.title,ready:document.readyState,composer:!!composer,composerTag:composer?.tagName?.toLowerCase()||null,composerText:text,submit:!!submit,submitText:submit?norm(submit):'',submitType:submit?.getAttribute('type')||null,stop:!!stop,blockedBy:block,bodyLength:body.length};
    })()`);
  }

  async waitComposer(timeout=45000){
    const deadline=now()+timeout;
    while(now()<deadline){
      const s=await this.uiState();
      if(s.composer&&s.ready!=='loading')return s;
      await sleep(400);
    }
    throw new Error('COMPOSER_NOT_READY');
  }

  async waitIdle(timeout=90000){
    const deadline=now()+timeout;let stable=0;
    while(now()<deadline){
      const s=await this.uiState();
      if(s.blockedBy)throw new Error(`BLOCKED:${s.blockedBy}`);
      if(s.composer&&!s.stop){stable++;if(stable>=4)return true;}else stable=0;
      await sleep(350);
    }
    return false;
  }

  async findComposerInfo(){
    return this.eval(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const pats=${this.patternsJs(this.config.composerPatterns)};const norm=e=>String(e?.getAttribute?.('aria-label')||e?.getAttribute?.('placeholder')||e?.innerText||e?.textContent||'').trim();const match=(t)=>pats.some(p=>{try{return new RegExp(p,'i').test(t)}catch{return false}});const all=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);const e=all.find(x=>match(norm(x)))||all.find(x=>x.tagName==='TEXTAREA')||all.find(x=>x.getAttribute('contenteditable')==='true')||all.find(x=>x.getAttribute('role')==='textbox')||null;if(!e)return null;e.focus();return {tag:e.tagName.toLowerCase(),type:e.getAttribute('type'),editable:e.getAttribute('contenteditable')};})()`);
  }

  async setComposer(text){
    const info=await this.findComposerInfo();
    if(!info)throw new Error('COMPOSER_NOT_FOUND');
    if(info.tag==='textarea'||info.tag==='input'){
      const payload=JSON.stringify(text);
      const ok=await this.eval(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const pats=${this.patternsJs(this.config.composerPatterns)};const norm=e=>String(e?.getAttribute?.('aria-label')||e?.getAttribute?.('placeholder')||'').trim();const match=t=>pats.some(p=>{try{return new RegExp(p,'i').test(t)}catch{return false}});const all=[...document.querySelectorAll('textarea,input')].filter(visible);const e=all.find(x=>match(norm(x)))||all.find(x=>x.tagName==='TEXTAREA')||all[0];if(!e)return false;e.focus();let proto=e,d=null;while(proto&&!d){proto=Object.getPrototypeOf(proto);if(proto)d=Object.getOwnPropertyDescriptor(proto,'value')}if(d?.set)d.set.call(e,${payload});else e.value=${payload};try{e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:${payload}}))}catch{e.dispatchEvent(new Event('input',{bubbles:true}))}e.dispatchEvent(new Event('change',{bubbles:true}));return true;})()`);
      if(!ok)throw new Error('COMPOSER_NATIVE_SET_FAILED');
    }else{
      await this.call('Input.dispatchKeyEvent',{type:'rawKeyDown',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
      await this.call('Input.dispatchKeyEvent',{type:'keyUp',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
      await this.call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
      await this.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
      await this.call('Input.insertText',{text});
    }
    await sleep(350);
    const s=await this.uiState();
    if(!s.composerText.includes(text.slice(0,Math.min(36,text.length))))throw new Error('COMPOSER_TEXT_NOT_SET');
    return s;
  }

  async waitSubmitReady(timeout=12000){
    const deadline=now()+timeout;
    while(now()<deadline){const s=await this.uiState();if(s.submit)return s;await sleep(200);}return null;
  }

  async clickSubmit(){
    return this.eval(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const pats=${this.patternsJs(this.config.submitPatterns)};const norm=e=>String(e?.getAttribute?.('aria-label')||e?.innerText||e?.value||'').trim();const match=t=>pats.some(p=>{try{return new RegExp(p,'i').test(t)}catch{return false}});const all=[...document.querySelectorAll('button,[role="button"],input[type="submit"]')].filter(visible);const e=all.find(x=>match(norm(x))&&!x.disabled&&x.getAttribute('aria-disabled')!=='true')||all.find(x=>x.getAttribute('type')==='submit'&&!x.disabled&&x.getAttribute('aria-disabled')!=='true');if(!e)return false;e.click();return true;})()`);
  }

  async submitNearestForm(){
    return this.eval(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const pats=${this.patternsJs(this.config.composerPatterns)};const norm=e=>String(e?.getAttribute?.('aria-label')||e?.getAttribute?.('placeholder')||e?.innerText||e?.textContent||'').trim();const match=t=>pats.some(p=>{try{return new RegExp(p,'i').test(t)}catch{return false}});const all=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);const e=all.find(x=>match(norm(x)))||all.find(x=>x.tagName==='TEXTAREA')||all.find(x=>x.getAttribute('contenteditable')==='true')||all.find(x=>x.getAttribute('role')==='textbox')||null;if(!e)return false;const f=e.closest('form');if(!f)return false;try{if(typeof f.requestSubmit==='function')f.requestSubmit();else f.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));return true}catch{return false}})()`);
  }

  async pressEnter(){
    const info=await this.findComposerInfo();if(!info)return false;
    await this.call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13});
    await this.call('Input.dispatchKeyEvent',{type:'char',text:'\r',unmodifiedText:'\r',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13}).catch(()=>{});
    await this.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13});
    return true;
  }

  async verifySubmitted(requestMarker,timeout=10000){
    const deadline=now()+timeout;
    while(now()<deadline){
      const s=await this.uiState();const b=await this.bodyText();
      if(!s.composerText.includes(requestMarker)&&(b.includes(requestMarker)||s.stop||s.composerText.trim()===''))return true;
      await sleep(250);
    }
    return false;
  }

  async submitPrompt(prompt,requestMarker){
    if(!await this.waitIdle())throw new Error('NOT_IDLE_BEFORE_SEND');
    await this.setComposer(prompt);
    const attempts=[];
    const ready=await this.waitSubmitReady(this.config.submitWaitMs||8000);
    if(ready&&await this.clickSubmit()){
      attempts.push('button');if(await this.verifySubmitted(requestMarker,7000))return 'button';
    }
    if(this.config.enterSubmit!==false&&await this.pressEnter()){
      attempts.push('enter');if(await this.verifySubmitted(requestMarker,7000))return 'enter';
    }
    if(await this.submitNearestForm()){
      attempts.push('form');if(await this.verifySubmitted(requestMarker,7000))return 'form';
    }
    throw new Error(`PROMPT_NOT_SUBMITTED:${attempts.join('+')||'none'}`);
  }

  async freshChat(){
    if(this.config.freshChat===false)return false;
    const clicked=await this.eval(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const els=[...document.querySelectorAll('a,button,[role="button"]')].filter(visible);const e=els.find(x=>/^new\s+(chat|conversation)(?:\s|$)/i.test(String(x.innerText||x.getAttribute('aria-label')||'').trim()));if(!e)return false;e.click();return true;})()`).catch(()=>false);
    if(clicked){await sleep(1000);await this.waitComposer(30000);}return clicked;
  }

  async health(){
    const started=now();
    try{
      await this.connect();const s=await this.waitComposer(30000);const status=s.blockedBy?'blocked':'ok';
      return this.lastHealth={status,text:status==='ok'?'browser/session/composer ready':`blocked:${s.blockedBy}`,metadata:{agent_id:this.id,port:this.port,url:s.href,title:s.title,composer_tag:s.composerTag,latency_ms:now()-started}};
    }catch(e){return this.lastHealth={status:'error',text:e.message,metadata:{agent_id:this.id,port:this.port,latency_ms:now()-started}};}
  }

  async waitEnvelope(begin,end,timeout=180000,expectedText=null,baselineExpectedCount=0){
    const deadline=now()+timeout;let last='';let stable=0;
    while(now()<deadline){
      const s=await this.uiState();
      if(s.blockedBy)throw new Error(`BLOCKED:${s.blockedBy}`);
      const b=await this.bodyText();
      const begins=b.split(begin).length-1;
      if(begins>=2){
        const i=b.lastIndexOf(begin);const j=b.indexOf(end,i+begin.length);
        if(j>i){
          const value=b.slice(i+begin.length,j).trim();
          if(value===last)stable++;else{last=value;stable=1;}
          if(stable>=2&&await this.waitIdle(20000))return value;
        }
      }
      if(expectedText){
        const count=b.split(expectedText).length-1;
        // One new occurrence is the submitted user prompt itself. Require a
        // second new occurrence so the proof necessarily includes provider
        // output rather than merely echoing HIVE's own prompt in the DOM.
        if(count>baselineExpectedCount+1&&!s.stop){
          await sleep(700);
          return expectedText;
        }
      }
      await sleep(500);
    }
    throw new Error('RESPONSE_ENVELOPE_TIMEOUT');
  }

  async run(task,options={}){
    const started=now();
    const nonce=crypto.randomBytes(6).toString('hex').toUpperCase();
    const requestMarker=`HIVE_ADAPTER_REQUEST:${this.id}:${nonce}`;
    const begin=`HIVE_ADAPTER_BEGIN:${this.id}:${nonce}`;
    const end=`HIVE_ADAPTER_END:${this.id}:${nonce}`;
    try{
      await this.connect();
      const hs=await this.waitComposer(30000);
      if(hs.blockedBy)return {status:'blocked',text:`blocked:${hs.blockedBy}`,metadata:{agent_id:this.id,port:this.port,url:hs.href}};
      const fresh=options.fresh??this.fresh;
      const freshOpened=fresh?await this.freshChat():false;
      const expectedText=options.expectedText?String(options.expectedText):null;
      const before=await this.bodyText();
      const baselineExpectedCount=expectedText?before.split(expectedText).length-1:0;
      const prompt=`${requestMarker}\
USER_TASK:\
${String(task)}\
\
OUTPUT_PROTOCOL:\
Execute USER_TASK. Put the actual final answer between the two exact markers below. Do not output placeholder words, XML tags, angle brackets, or the request marker.\
${begin}\
FINAL_ANSWER_TO_USER_TASK\
${end}\
Replace FINAL_ANSWER_TO_USER_TASK with the real answer.`;
      const submitMethod=await this.submitPrompt(prompt,requestMarker);
      const text=await this.waitEnvelope(begin,end,options.timeoutMs||this.config.timeoutMs||180000,expectedText,baselineExpectedCount);
      const s=await this.uiState();
      return {status:'ok',text,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,url:s.href,fresh_chat:freshOpened,submit_method:submitMethod,transport:'browser-cdp',zero_cost_path:true,latency_ms:now()-started,nonce}};
    }catch(e){
      const blocked=/^BLOCKED:/.test(e.message);
      return {status:blocked?'blocked':'error',text:e.message,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,transport:'browser-cdp',zero_cost_path:true,latency_ms:now()-started,nonce}};
    }
  }

  close(){try{this.ws?.close();}catch{}this.ws=null;}
}
