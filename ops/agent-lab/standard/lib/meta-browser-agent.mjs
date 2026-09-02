import { MarkerBrowserAgent } from './marker-browser-agent.mjs';

const sleep=ms=>new Promise(r=>setTimeout(r,ms));

export class MetaBrowserAgent extends MarkerBrowserAgent {
  metaComposerExpr(){
    return `(()=>{
      const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const test=[...document.querySelectorAll('[data-testid="composer-input"]')];
      const onScreen=test.find(e=>visible(e)&&e.tagName!=='TEXTAREA')||test.find(visible)||null;
      if(onScreen)return onScreen;
      const all=[...document.querySelectorAll('input,textarea,[contenteditable="true"],[role="textbox"]')].filter(visible);
      return all.find(x=>/ask meta ai|message meta ai/i.test(String(x.getAttribute('aria-label')||x.getAttribute('placeholder')||'')))||all.find(x=>x.getAttribute('contenteditable')==='true'&&x.getAttribute('role')==='textbox')||all.find(x=>x.getAttribute('contenteditable')==='true')||all.find(x=>x.tagName==='TEXTAREA')||all.find(x=>x.getAttribute('role')==='textbox')||null;
    })()`;
  }

  async metaUiState(){
    const expr=this.metaComposerExpr();
    return this.eval(`(()=>{
      const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const composer=(${expr});
      const controls=[...document.querySelectorAll('button,a,[role="button"]')].filter(visible);
      const send=document.querySelector('[data-testid="composer-send-button"]')||controls.find(e=>/^send$/i.test(String(e.getAttribute('aria-label')||e.innerText||'').trim()))||null;
      const stop=document.querySelector('[data-testid="composer-stop-button"]')||controls.find(e=>/^(stop|stop generating|stop responding|cancel response)$/i.test(String(e.getAttribute('aria-label')||e.innerText||'').trim()))||null;
      const mirrors=[...document.querySelectorAll('textarea[data-testid="composer-input"]')];
      const mirror=mirrors[0]||null;
      const dialogs=[...document.querySelectorAll('[role="dialog"],[aria-modal="true"]')].filter(visible).map(e=>String(e.innerText||e.textContent||''));
      const authInput=!!document.querySelector('input[type="password"],input[type="email"],input[type="tel"]');
      const loginControl=controls.some(e=>/(^|\\b)(log\\s*in|sign\\s*in|continue\\s+with|accedi)(\\b|$)/i.test(String(e.innerText||e.getAttribute('aria-label')||'').trim()));
      const loginDialog=dialogs.some(t=>/log in to meta ai|continue with facebook|continue with instagram|continue with email|sign in to meta ai/i.test(t));
      const text=mirror?String(mirror.value||''):(composer?String(composer.value||composer.innerText||composer.textContent||''):'');
      return {
        href:String(location.href||''),ready:document.readyState,composer:!!composer,composerText:text,
        composerTag:composer?.tagName?.toLowerCase()||null,
        sendVisible:!!send&&visible(send),sendDisabled:send?!!send.disabled||send.getAttribute('aria-disabled')==='true':null,
        stopVisible:!!stop&&visible(stop),loginVisible:!composer&&(loginDialog||(authInput&&loginControl)),
        assistantCount:document.querySelectorAll('[data-testid="assistant-message"]').length
      };
    })()`);
  }

  async metaNavigateHome(){
    await this.call('Page.navigate',{url:'https://www.meta.ai/'},12000);
    await sleep(2200);
  }

  async metaReload(){
    await this.call('Page.reload',{ignoreCache:false},12000).catch(()=>{});
    await sleep(1800);
  }

  async metaWaitComposer(timeout=45000,{repair=true}={}){
    const started=Date.now(),deadline=started+timeout;
    let navigated=false,reloaded=false,last=null;
    while(Date.now()<deadline){
      const s=await this.metaUiState();
      last=s;
      if(s.loginVisible)throw new Error('BLOCKED:META_LOGIN_REQUIRED');
      if(s.composer&&s.ready!=='loading')return s;
      const elapsed=Date.now()-started;
      if(repair&&!navigated&&elapsed>=7000){
        await this.metaNavigateHome().catch(()=>{});
        navigated=true;
      }else if(repair&&navigated&&!reloaded&&elapsed>=18000){
        await this.metaReload().catch(()=>{});
        reloaded=true;
      }
      await sleep(350);
    }
    if(last?.loginVisible)throw new Error('BLOCKED:META_LOGIN_REQUIRED');
    throw new Error(repair?'META_COMPOSER_NOT_READY_AFTER_PAGE_RECOVERY':'META_COMPOSER_NOT_READY');
  }

  async metaWaitIdle(timeout=60000){
    const deadline=Date.now()+timeout;let stable=0;
    while(Date.now()<deadline){
      const s=await this.metaUiState();
      if(s.loginVisible)throw new Error('BLOCKED:META_LOGIN_REQUIRED');
      if(s.composer&&!s.stopVisible){stable++;if(stable>=4)return true;}else stable=0;
      await sleep(350);
    }
    return false;
  }

  async focusMetaComposer(){
    const expr=this.metaComposerExpr();
    return this.eval(`(()=>{const e=(${expr});if(!e)return false;e.focus();return true;})()`);
  }

  async clearMetaComposer(){
    if(!await this.focusMetaComposer())throw new Error('META_COMPOSER_NOT_FOUND');
    await this.call('Input.dispatchKeyEvent',{type:'rawKeyDown',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
    await this.call('Input.dispatchKeyEvent',{type:'keyUp',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
    await this.call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
    await this.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
    await sleep(250);
  }

  async setMetaComposer(text){
    await this.clearMetaComposer();
    await this.call('Input.insertText',{text:String(text)});
    await sleep(450);
    const s=await this.metaUiState();
    if(!s.composerText.includes(String(text).slice(0,Math.min(36,String(text).length))))throw new Error('META_TEXT_NOT_INSERTED');
    return s;
  }

  async clickMetaSend(){
    return this.eval(`(()=>{
      const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const e=document.querySelector('[data-testid="composer-send-button"]')||[...document.querySelectorAll('button,[role="button"]')].filter(visible).find(x=>/^send$/i.test(String(x.getAttribute('aria-label')||x.innerText||'').trim()));
      if(!e||!visible(e)||e.disabled||e.getAttribute('aria-disabled')==='true')return false;e.click();return true;
    })()`);
  }

  async pressMetaEnter(){
    if(!await this.focusMetaComposer())return false;
    await this.call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    await this.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    return true;
  }

  async metaAssistantSnapshot(){
    return this.eval(`(()=>{
      const items=[...document.querySelectorAll('[data-testid="assistant-message"]')];
      const item=items[items.length-1]||null;
      if(!item)return {count:0,text:''};
      const clone=item.cloneNode(true);
      clone.querySelectorAll('[data-testid="thinking-status"],[data-testid="subagent-cot-list"]').forEach(e=>e.remove());
      return {count:items.length,text:String(clone.innerText||clone.textContent||'').trim()};
    })()`);
  }

  async submitMetaExact(prompt,marker){
    if(!await this.metaWaitIdle(60000))throw new Error('META_NOT_IDLE_BEFORE_SEND');
    const before=(await this.metaUiState()).assistantCount;
    let s=await this.setMetaComposer(prompt);
    let method='SEND_BUTTON';
    if(!(s.sendVisible&&!s.sendDisabled&&await this.clickMetaSend())){
      method='ENTER';
      if(!await this.pressMetaEnter())throw new Error('META_SUBMIT_CONTROL_NOT_FOUND');
    }
    const deadline=Date.now()+15000;
    while(Date.now()<deadline){
      s=await this.metaUiState();
      if(s.loginVisible)throw new Error('BLOCKED:META_LOGIN_REQUIRED');
      if(!s.composerText.includes(marker)&&(s.assistantCount>before||s.stopVisible||s.composerText.trim()===''))return method;
      await sleep(300);
    }
    throw new Error('META_PROMPT_NOT_SUBMITTED');
  }

  async health(){
    const started=Date.now();
    try{
      await this.connect();
      const s=await this.metaWaitComposer(30000,{repair:true});
      return {status:'ok',text:'meta browser/session/composer ready',metadata:{agent_id:this.id,port:this.port,url:s.href,composer_tag:s.composerTag,latency_ms:Date.now()-started}};
    }catch(e){
      const message=String(e?.message||e||'META_HEALTH_ERROR');
      const blocked=/^BLOCKED:/.test(message);
      return {status:blocked?'blocked':'error',text:message,metadata:{agent_id:this.id,port:this.port,latency_ms:Date.now()-started}};
    }
  }

  async run(task,options={}){
    const expectedText=options.expectedText?String(options.expectedText):null;
    if(!expectedText)return super.run(task,options);
    const started=Date.now();
    const requestMarker=`HIVE_META_PROBE:${Date.now()}:${Math.random().toString(16).slice(2,10)}`;
    try{
      await this.connect();
      const state=await this.metaWaitComposer(45000,{repair:true});
      const before=await this.metaAssistantSnapshot();
      const prompt=`${requestMarker}\nReply EXACTLY with the token below. Do not add punctuation, markdown or explanation.\n${expectedText}`;
      const submitMethod=await this.submitMetaExact(prompt,requestMarker);
      const deadline=Date.now()+(options.timeoutMs||this.config.timeoutMs||180000);
      let stableText=null,stable=0;
      while(Date.now()<deadline){
        const s=await this.metaUiState();
        if(s.loginVisible)throw new Error('BLOCKED:META_LOGIN_REQUIRED');
        const snap=await this.metaAssistantSnapshot();
        if(snap.count>before.count&&snap.text&&!s.stopVisible){
          if(snap.text===stableText)stable++;else{stableText=snap.text;stable=1;}
          if(stable>=3){
            if(snap.text===expectedText)return {status:'ok',text:expectedText,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,url:s.href||state.href,fresh_chat:false,fresh_policy:'provider-segment-proof',submit_method:submitMethod,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started,capture:'meta-assistant-testid-exact-token'}};
            return {status:'error',text:'META_EXACT_OUTPUT_MISMATCH',metadata:{agent_id:this.id,provider:this.config.product,port:this.port,url:s.href||state.href,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started,capture:'meta-assistant-testid-mismatch',submit_method:submitMethod,response_length:snap.text.length}};
          }
        }
        await sleep(650);
      }
      throw new Error('META_EXACT_TOKEN_TIMEOUT');
    }catch(e){
      const message=String(e?.message||e||'META_RUN_ERROR');
      const blocked=/^BLOCKED:/.test(message);
      return {status:blocked?'blocked':'error',text:message,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started}};
    }
  }

  async recover(reason='unknown'){
    this.close();
    try{
      await this.connect();
      await this.metaNavigateHome().catch(()=>{});
      await this.metaWaitComposer(30000,{repair:true});
      return {recovered:true,method:'meta-page-recovery',reason,port:this.port};
    }catch(e){
      this.close();
      return {recovered:false,method:'meta-page-recovery',reason,error:String(e?.message||e)};
    }
  }
}
