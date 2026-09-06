import { KeyboardBrowserAgent } from './keyboard-browser-agent.mjs';

const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const retryableCdp=e=>/CDP_TIMEOUT_(Runtime\.enable|Runtime\.evaluate|Page\.enable)|CDP_CONNECT_(TIMEOUT|ERROR)|PAGE_WEBSOCKET_NOT_FOUND|WebSocket|InvalidStateError/i.test(String(e?.message||e||''));
const KIMI_RELAY_TASK='https://r.jina.ai/https://hive-kimi-relay.project-giovanni.workers.dev/work';

export class KimiBrowserAgent extends KeyboardBrowserAgent {
  usable(url=''){
    try{
      const u=new URL(String(url));
      return /(^|\.)kimi\.ai$/i.test(u.hostname)&&!/^\/(?:auth|login|oauth|account)(?:\/|$)/i.test(u.pathname);
    }catch{return false;}
  }

  async targets(){
    const r=await fetch(`http://127.0.0.1:${this.port}/json/list`,{signal:AbortSignal.timeout(4000)});
    if(!r.ok)throw new Error(`KIMI_TARGET_LIST_HTTP_${r.status}`);
    return r.json();
  }

  async openHome(){
    const base=`http://127.0.0.1:${this.port}`;
    const r=await fetch(`${base}/json/new?${encodeURIComponent('https://www.kimi.ai/')}`,{method:'PUT',signal:AbortSignal.timeout(7000)});
    if(!r.ok)throw new Error(`KIMI_TARGET_OPEN_HTTP_${r.status}`);
    const t=await r.json();
    if(t?.id)await fetch(`${base}/json/activate/${encodeURIComponent(t.id)}`,{signal:AbortSignal.timeout(3500)}).catch(()=>null);
    await sleep(1600);
    return t;
  }

  async ensureBrowser(){
    const fallback=await super.ensureBrowser();
    try{
      const pages=(await this.targets()).filter(t=>t?.type==='page'&&t.webSocketDebuggerUrl);
      const hit=pages.find(t=>this.usable(t.url)&&/\/chat\//i.test(String(t.url||'')))||pages.find(t=>this.usable(t.url));
      if(hit)return hit;
      const t=await this.openHome();
      if(t?.webSocketDebuggerUrl)return t;
    }catch{}
    if(fallback&&this.usable(fallback.url))return fallback;
    throw new Error('KIMI_USABLE_TARGET_NOT_FOUND');
  }

  async recycleTarget(){
    this.close();
    try{
      const base=`http://127.0.0.1:${this.port}`;
      const all=await this.targets();
      for(const t of all.filter(x=>x?.type==='page'&&this.config.targetPattern.test(String(x.url||'')))){
        if(t.id)await fetch(`${base}/json/close/${encodeURIComponent(t.id)}`,{signal:AbortSignal.timeout(3500)}).catch(()=>null);
      }
      await sleep(600);
      return !!(await this.openHome())?.webSocketDebuggerUrl;
    }catch{return false;}
  }

  async connect(){
    let last=null;
    for(let i=1;i<=3;i++){
      try{
        if(this.ws?.readyState===WebSocket.OPEN){
          await this.call('Runtime.evaluate',{expression:'1',returnByValue:true},6000);
          return;
        }
        await super.connect();
        await this.call('Runtime.evaluate',{expression:'1',returnByValue:true},7000);
        return;
      }catch(e){
        last=e;this.close();
        if(!retryableCdp(e))throw e;
        if(i===1){await sleep(700);continue;}
        await this.recycleTarget().catch(()=>false);
        await sleep(700*i);
      }
    }
    throw new Error(`KIMI_CDP_RECOVERY_EXHAUSTED:${String(last?.message||last||'unknown')}`);
  }

  async ui(){
    return this.eval(`(()=>{
      const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const editors=[...document.querySelectorAll('.chat-input-editor,[data-lexical-editor="true"],[contenteditable="true"][role="textbox"],[contenteditable="true"]')].filter(visible);
      const editor=editors.find(e=>e.matches('.chat-input-editor')&&e.closest('.chat-editor'))||editors.find(e=>e.matches('.chat-input-editor'))||editors.find(e=>e.getAttribute('data-lexical-editor')==='true')||editors[editors.length-1]||null;
      const send=[...document.querySelectorAll('.send-button-container')].filter(visible).pop()||null;
      const controls=[...document.querySelectorAll('button,a,[role="button"]')].filter(visible);
      const authInput=!!document.querySelector('input[type="password"],input[type="email"],input[type="tel"]');
      const authControl=controls.some(e=>/(log\\s*in|sign\\s*in|continue\\s+with|accedi|se connecter|登录|登入|手机号|邮箱)/i.test(String(e.innerText||e.textContent||e.getAttribute('aria-label')||'')));
      const body=String(document.body?.innerText||'');
      const authText=/(log\\s*in\\s+to\\s+kimi|sign\\s*in\\s+to\\s+kimi|continue\\s+with\\s+(google|apple|phone)|登录|登入|手机号|手机号码|邮箱)/i.test(body);
      return {
        href:String(location.href||''),ready:document.readyState,composer:!!editor,
        composerText:editor?String(editor.textContent||editor.innerText||''):'',
        sendVisible:!!send,sendDisabled:send?send.classList.contains('disabled')||send.getAttribute('aria-disabled')==='true'||getComputedStyle(send).pointerEvents==='none':true,
        generating:!!send&&send.classList.contains('stop'),
        userCount:document.querySelectorAll('.segment.segment-user,.segment-user').length,
        assistantCount:document.querySelectorAll('.segment.segment-assistant,.segment-assistant').length,
        loginVisible:!editor&&(authText||(authInput&&authControl))
      };
    })()`);
  }

  async dismissQuotaModal(){
    const clicked=await this.eval(`(()=>{
      const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const body=String(document.body?.innerText||'');
      if(!/(credits? used up|free quota is used up|quota gratuita.{0,40}esaurita|quota.{0,40}esaurita)/i.test(body))return false;
      const controls=[...document.querySelectorAll('button,[role="button"]')].filter(visible);
      const ok=controls.find(e=>/^(got it|ok|capito|ho capito|va bene|entendido|知道了)$/i.test(String(e.innerText||e.textContent||'').trim()));
      if(ok){ok.click();return true;}
      const close=controls.find(e=>/close|chiudi/i.test(String(e.getAttribute('aria-label')||e.title||'')));
      if(close){close.click();return true;}
      return false;
    })()`).catch(()=>false);
    if(clicked)await sleep(700);
    return clicked;
  }

  async navigateHome(){
    await this.call('Page.navigate',{url:'https://www.kimi.ai/'},12000);
    await sleep(2200);
  }

  async waitComposer(timeout=45000,repair=true){
    const start=Date.now(),deadline=start+timeout;
    let nav=false,reload=false,last=null;
    while(Date.now()<deadline){
      const s=await this.ui();last=s;
      if(s.loginVisible)throw new Error('BLOCKED:KIMI_LOGIN_REQUIRED');
      if(s.composer&&s.ready!=='loading')return s;
      const elapsed=Date.now()-start;
      if(repair&&!nav&&elapsed>6500){await this.navigateHome().catch(()=>{});nav=true;}
      else if(repair&&nav&&!reload&&elapsed>17000){await this.call('Page.reload',{ignoreCache:false},12000).catch(()=>{});await sleep(1700);reload=true;}
      await sleep(350);
    }
    if(last?.loginVisible)throw new Error('BLOCKED:KIMI_LOGIN_REQUIRED');
    throw new Error(repair?'KIMI_COMPOSER_NOT_READY_AFTER_PAGE_RECOVERY':'KIMI_COMPOSER_NOT_READY');
  }

  async waitKimiIdle(timeout=60000){
    const deadline=Date.now()+timeout;let stable=0;
    while(Date.now()<deadline){
      const s=await this.ui();
      if(s.loginVisible)throw new Error('BLOCKED:KIMI_LOGIN_REQUIRED');
      if(s.composer&&!s.generating){if(++stable>=4)return true;}else stable=0;
      await sleep(300);
    }
    return false;
  }

  async assistant(){
    return this.eval(`(()=>{
      const items=[...document.querySelectorAll('.segment.segment-assistant,.segment-assistant')];
      const item=items[items.length-1]||null;
      if(!item)return {count:0,text:''};
      const body=item.querySelector('.segment-content-box')||item.querySelector('.segment-content')||item;
      const clone=body.cloneNode(true);
      clone.querySelectorAll('.thinking-container').forEach(e=>e.remove());
      return {count:items.length,text:String(clone.innerText||clone.textContent||'').trim()};
    })()`);
  }

  async setKimiInput(text){
    const payload=JSON.stringify(String(text));
    const probe=JSON.stringify(String(text).slice(0,Math.min(32,String(text).length)));
    const ok=await this.eval(`(()=>{
      const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const all=[...document.querySelectorAll('.chat-input-editor,[data-lexical-editor="true"],[contenteditable="true"][role="textbox"]')].filter(visible);
      const e=all.find(x=>x.matches('.chat-input-editor')&&x.closest('.chat-editor'))||all.find(x=>x.matches('.chat-input-editor'))||all.find(x=>x.getAttribute('data-lexical-editor')==='true')||all[all.length-1]||null;
      if(!e)return false;e.focus();
      try{const sel=getSelection(),range=document.createRange();range.selectNodeContents(e);sel.removeAllRanges();sel.addRange(range);document.execCommand('insertText',false,${payload});}
      catch{return false;}
      try{e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:${payload}}))}catch{e.dispatchEvent(new Event('input',{bubbles:true}))}
      return String(e.textContent||e.innerText||'').includes(${probe});
    })()`).catch(()=>false);
    if(!ok)await super.setComposer(text);
    await sleep(400);
    const s=await this.ui();
    if(!s.composerText.includes(String(text).slice(0,Math.min(32,String(text).length))))throw new Error('KIMI_TEXT_NOT_INSERTED');
  }

  async clickSend(){
    return this.eval(`(()=>{const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const e=[...document.querySelectorAll('.send-button-container')].filter(visible).pop()||null;if(!e||e.classList.contains('stop')||e.classList.contains('disabled')||e.getAttribute('aria-disabled')==='true'||getComputedStyle(e).pointerEvents==='none')return false;e.click();return true;})()`).catch(()=>false);
  }

  async submitted(marker,before,timeout=12000){
    const deadline=Date.now()+timeout;
    while(Date.now()<deadline){
      const s=await this.ui();
      if(s.loginVisible)throw new Error('BLOCKED:KIMI_LOGIN_REQUIRED');
      if(!s.composerText.includes(marker)&&(s.userCount>before||s.generating||s.composerText.trim()===''))return true;
      await sleep(250);
    }
    return false;
  }

  async submit(prompt,marker){
    await this.dismissQuotaModal().catch(()=>false);
    if(!await this.waitKimiIdle())throw new Error('KIMI_NOT_IDLE_BEFORE_SEND');
    const before=(await this.ui()).userCount;
    await this.setKimiInput(prompt);
    await this.dismissQuotaModal().catch(()=>false);

    const genericReady=await this.waitSubmitReady(5000).catch(()=>null);
    if(genericReady&&await this.clickSubmit().catch(()=>false)){
      if(await this.submitted(marker,before,8000))return 'generic-send-button';
    }

    const ready=Date.now()+5000;
    while(Date.now()<ready){const s=await this.ui();if(s.sendVisible&&!s.sendDisabled&&!s.generating)break;await sleep(200);}
    if(await this.clickSend())if(await this.submitted(marker,before))return 'kimi-send-container';
    if(await this.pressEnter())if(await this.submitted(marker,before,10000))return 'cdp-enter';
    throw new Error('KIMI_PROMPT_NOT_SUBMITTED');
  }

  async run(task,options={}){
    const expectedText=options.expectedText?String(options.expectedText):null;
    if(!expectedText)return super.run(task,options);
    const started=Date.now(),marker=`HIVE_KIMI_PROBE:${Date.now()}:${Math.random().toString(16).slice(2,10)}`;
    try{
      await this.connect();
      const state=await this.waitComposer(45000,true);
      const before=await this.assistant();
      const relayPrompt=`${marker}\nUse web_open_url to open this URL and execute the HIVE task exactly as instructed:\n${KIMI_RELAY_TASK}\nAfter the callback response confirms accepted=true and certified=true, return exactly this token and nothing else. Do not use markdown, quotes, punctuation or explanation:\n${expectedText}`;
      const method=await this.submit(relayPrompt,marker);
      const deadline=Date.now()+(options.timeoutMs||this.config.timeoutMs||180000);
      let last='',stable=0;
      while(Date.now()<deadline){
        const s=await this.ui();
        if(s.loginVisible)throw new Error('BLOCKED:KIMI_LOGIN_REQUIRED');
        const a=await this.assistant();
        if(a.count>before.count&&a.text&&!s.generating){
          if(a.text===last)stable++;else{last=a.text;stable=1;}
          if(stable>=3){
            if(a.text===expectedText)return {status:'ok',text:expectedText,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,url:s.href||state.href,transport:'browser-cdp-jina-relay',zero_cost_path:true,latency_ms:Date.now()-started,capture:'kimi-assistant-segment-exact',submit_method:method,relay_task:KIMI_RELAY_TASK}};
            return {status:'error',text:'KIMI_EXACT_OUTPUT_MISMATCH',metadata:{agent_id:this.id,provider:this.config.product,port:this.port,transport:'browser-cdp-jina-relay',zero_cost_path:true,latency_ms:Date.now()-started,response_length:a.text.length}};
          }
        }
        await sleep(650);
      }
      throw new Error('KIMI_EXACT_RESPONSE_TIMEOUT');
    }catch(e){
      const message=String(e?.message||e||'KIMI_RUN_ERROR');
      return {status:/^BLOCKED:/i.test(message)?'blocked':'error',text:message,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,transport:'browser-cdp-jina-relay',zero_cost_path:true,latency_ms:Date.now()-started}};
    }
  }

  async recover(reason='unknown'){
    this.close();
    try{
      await this.connect();
      await this.waitComposer(20000,false);
      return {recovered:true,method:'kimi-session-reconnect',reason,port:this.port};
    }catch{}
    if(!await this.recycleTarget().catch(()=>false))return {recovered:false,method:'kimi-target-recycle',reason};
    try{
      await this.connect();
      await this.navigateHome().catch(()=>{});
      await this.waitComposer(30000,true);
      return {recovered:true,method:'kimi-page-target-recovery',reason,port:this.port};
    }catch(e){
      this.close();
      return {recovered:false,method:'kimi-page-target-recovery',reason,error:String(e?.message||e)};
    }
  }
}
