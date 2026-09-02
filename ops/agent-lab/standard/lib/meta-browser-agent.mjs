import { MarkerBrowserAgent } from './marker-browser-agent.mjs';

const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const count=(text,token)=>token?String(text||'').split(token).length-1:0;

export class MetaBrowserAgent extends MarkerBrowserAgent {
  metaComposerExpr(){
    return `(()=>{const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const tested=[...document.querySelectorAll('[data-testid="composer-input"]')].filter(visible);const preferred=tested.find(x=>x.tagName!=='TEXTAREA')||tested[0]||null;if(preferred)return preferred;const all=[...document.querySelectorAll('input,textarea,[contenteditable="true"],[role="textbox"]')].filter(visible);return all.find(x=>/ask meta ai|message meta ai/i.test(String(x.getAttribute('aria-label')||x.getAttribute('placeholder')||'')))||all.find(x=>x.getAttribute('contenteditable')==='true'&&x.getAttribute('role')==='textbox')||all.find(x=>x.getAttribute('contenteditable')==='true')||all.find(x=>x.tagName==='TEXTAREA')||all.find(x=>x.getAttribute('role')==='textbox')||null;})()`;
  }

  async metaUiState(){
    const expr=this.metaComposerExpr();
    return this.eval(`(()=>{const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const composer=(${expr});const controls=[...document.querySelectorAll('button,a,[role="button"]')].filter(visible);const send=document.querySelector('[data-testid="composer-send-button"]')||controls.find(e=>/^send$/i.test(String(e.getAttribute('aria-label')||e.innerText||'').trim()));const stop=document.querySelector('[data-testid="composer-stop-button"]')||controls.find(e=>/^(stop|stop generating|stop responding|cancel response)$/i.test(String(e.getAttribute('aria-label')||e.innerText||'').trim()));const dialogs=[...document.querySelectorAll('[role="dialog"],[aria-modal="true"]')].filter(visible).map(e=>String(e.innerText||e.textContent||''));const authInput=!!document.querySelector('input[type="password"],input[type="email"],input[type="tel"]');const loginControl=controls.some(e=>/(^|\\b)(log\\s*in|sign\\s*in|continue\\s+with|accedi)(\\b|$)/i.test(String(e.innerText||e.getAttribute('aria-label')||'').trim()));const loginDialog=dialogs.some(t=>/log in to meta ai|continue with facebook|continue with instagram|continue with email|sign in to meta ai/i.test(t));const login=!composer&&(loginDialog||(authInput&&loginControl));return {href:String(location.href||''),ready:document.readyState,composer:!!composer,composerText:composer?String(composer.value||composer.innerText||composer.textContent||''):'',composerTag:composer?.tagName?.toLowerCase()||null,sendVisible:!!send&&visible(send),sendDisabled:send?!!send.disabled||send.getAttribute('aria-disabled')==='true':null,stopVisible:!!stop&&visible(stop),loginVisible:!!login};})()`);
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
      if(repair&&!navigated&&elapsed>=6500){await this.metaNavigateHome().catch(()=>{});navigated=true;}
      else if(repair&&navigated&&!reloaded&&elapsed>=17000){await this.metaReload().catch(()=>{});reloaded=true;}
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

  async clickMetaSend(){
    return this.eval(`(()=>{const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const e=document.querySelector('[data-testid="composer-send-button"]')||[...document.querySelectorAll('button,[role="button"]')].filter(visible).find(x=>/^send$/i.test(String(x.getAttribute('aria-label')||x.innerText||'').trim()));if(!e||!visible(e)||e.disabled||e.getAttribute('aria-disabled')==='true')return false;e.click();return true;})()`);
  }

  async pressMetaEnter(){
    if(!await this.focusMetaComposer())return false;
    await this.call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    await this.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    return true;
  }

  async submitMetaExact(prompt,marker){
    if(!await this.metaWaitIdle(60000))throw new Error('META_NOT_IDLE_BEFORE_SEND');
    await this.clearMetaComposer();
    await this.call('Input.insertText',{text:prompt});
    await sleep(500);
    let s=await this.metaUiState();
    if(!s.composerText.includes(marker))throw new Error('META_TEXT_NOT_INSERTED');
    let method='SEND_BUTTON';
    if(!(s.sendVisible&&!s.sendDisabled&&await this.clickMetaSend())){
      method='ENTER';
      if(!await this.pressMetaEnter())throw new Error('META_SUBMIT_CONTROL_NOT_FOUND');
    }
    const deadline=Date.now()+15000;
    while(Date.now()<deadline){
      s=await this.metaUiState();
      if(s.loginVisible)throw new Error('BLOCKED:META_LOGIN_REQUIRED');
      const body=await this.bodyText();
      if(!s.composerText.includes(marker)&&(body.includes(marker)||s.stopVisible||s.composerText.trim()===''))return method;
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
      const blocked=/^BLOCKED:/.test(String(e.message||''));
      return {status:blocked?'blocked':'error',text:String(e.message||'META_HEALTH_ERROR'),metadata:{agent_id:this.id,port:this.port,latency_ms:Date.now()-started}};
    }
  }

  async run(task,options={}){
    const expectedText=options.expectedText?String(options.expectedText):null;
    if(!expectedText)return super.run(task,options);
    const started=Date.now();
    const requestMarker=`HIVE_META_PROBE:${Date.now()}`;
    try{
      await this.connect();
      const state=await this.metaWaitComposer(45000,{repair:true});
      const baseline=count(await this.bodyText(),expectedText);
      const prompt=`${requestMarker}\nReply EXACTLY with the token below. Do not add punctuation, markdown or explanation.\n${expectedText}`;
      const submitMethod=await this.submitMetaExact(prompt,requestMarker);
      const deadline=Date.now()+(options.timeoutMs||this.config.timeoutMs||180000);
      let stable=0,last=-1;
      while(Date.now()<deadline){
        const s=await this.metaUiState();
        if(s.loginVisible)throw new Error('BLOCKED:META_LOGIN_REQUIRED');
        const body=await this.bodyText();
        const n=count(body,expectedText);
        if(n>=baseline+2&&!s.stopVisible){
          if(n===last)stable++;else{last=n;stable=1;}
          if(stable>=3&&await this.metaWaitIdle(30000))return {status:'ok',text:expectedText,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,url:s.href||state.href,fresh_chat:false,fresh_policy:'nonce-baseline-no-reset',submit_method:submitMethod,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started,capture:'body-occurrence-exact-token'}};
        }
        await sleep(750);
      }
      throw new Error('META_EXACT_TOKEN_TIMEOUT');
    }catch(e){
      const blocked=/^BLOCKED:/.test(String(e.message||''));
      return {status:blocked?'blocked':'error',text:String(e.message||'META_RUN_ERROR'),metadata:{agent_id:this.id,provider:this.config.product,port:this.port,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started}};
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
