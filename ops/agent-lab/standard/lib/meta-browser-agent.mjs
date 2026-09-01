import { MarkerBrowserAgent } from './marker-browser-agent.mjs';

const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const count=(text,token)=>token?String(text||'').split(token).length-1:0;

export class MetaBrowserAgent extends MarkerBrowserAgent {
  metaComposerExpr(){
    return `(()=>{
      const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const all=[...document.querySelectorAll('input,textarea,[contenteditable="true"],[role="textbox"]')].filter(visible);
      return all.find(x=>/ask meta ai|message meta ai/i.test(String(x.getAttribute('aria-label')||x.getAttribute('placeholder')||'')))
        || all.find(x=>x.getAttribute('contenteditable')==='true'&&x.getAttribute('role')==='textbox')
        || all.find(x=>x.getAttribute('contenteditable')==='true')
        || all.find(x=>x.tagName==='TEXTAREA')
        || all.find(x=>x.getAttribute('role')==='textbox')
        || all.find(x=>x.tagName==='INPUT')
        || null;
    })()`;
  }

  async metaComposerText(){
    const expr=this.metaComposerExpr();
    return this.eval(`(()=>{const e=(${expr});return e?String(e.value||e.innerText||e.textContent||''):'';})()`).catch(()=> '');
  }

  async focusMetaComposer(){
    const expr=this.metaComposerExpr();
    return this.eval(`(()=>{const e=(${expr});if(!e)return false;e.focus();return true;})()`);
  }

  async metaLoginGate(){
    return this.eval(`(()=>{
      const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const dialogs=[...document.querySelectorAll('[role="dialog"],[aria-modal="true"]')].filter(visible).map(e=>String(e.innerText||e.textContent||''));
      return dialogs.some(t=>/log in to meta ai|continue with facebook|continue with instagram|continue with email/i.test(t));
    })()`).catch(()=>false);
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
    return this.eval(`(()=>{
      const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const all=[...document.querySelectorAll('button,[role="button"]')].filter(visible);
      const e=all.find(x=>/^send$/i.test(String(x.getAttribute('aria-label')||x.innerText||'').trim()))
        ||all.find(x=>/send/i.test(String(x.getAttribute('aria-label')||x.getAttribute('title')||'').trim())&&!x.disabled&&x.getAttribute('aria-disabled')!=='true');
      if(!e||e.disabled||e.getAttribute('aria-disabled')==='true')return false;e.click();return true;
    })()`);
  }

  async pressMetaEnter(){
    if(!await this.focusMetaComposer())return false;
    await this.call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    await this.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    return true;
  }

  async submitMetaExact(prompt,marker){
    if(await this.metaLoginGate())throw new Error('BLOCKED:META_LOGIN_REQUIRED');
    if(!await this.waitIdle(60000))throw new Error('META_NOT_IDLE_BEFORE_SEND');
    await this.clearMetaComposer();
    await this.call('Input.insertText',{text:prompt});
    await sleep(500);
    if(!(await this.metaComposerText()).includes(marker))throw new Error('META_TEXT_NOT_INSERTED');
    let method='send-button';
    if(!await this.clickMetaSend()){
      method='enter';
      if(!await this.pressMetaEnter())throw new Error('META_SUBMIT_CONTROL_NOT_FOUND');
    }
    const deadline=Date.now()+15000;
    while(Date.now()<deadline){
      if(await this.metaLoginGate())throw new Error('BLOCKED:META_LOGIN_REQUIRED');
      const s=await this.uiState();
      const b=await this.bodyText();
      const composer=await this.metaComposerText();
      if(!composer.includes(marker)&&(b.includes(marker)||s.stop||composer.trim()===''))return method;
      await sleep(300);
    }
    throw new Error('META_PROMPT_NOT_SUBMITTED');
  }

  async run(task,options={}){
    const expectedText=options.expectedText?String(options.expectedText):null;
    if(!expectedText)return super.run(task,options);
    const started=Date.now();
    const requestMarker=`HIVE_META_PROBE:${Date.now()}`;
    try{
      await this.connect();
      const hs=await this.waitComposer(45000);
      if(hs.blockedBy)return {status:'blocked',text:`blocked:${hs.blockedBy}`,metadata:{agent_id:this.id,port:this.port,url:hs.href}};
      if(await this.metaLoginGate())return {status:'blocked',text:'blocked:META_LOGIN_REQUIRED',metadata:{agent_id:this.id,port:this.port,url:hs.href}};

      // Exact probes use a random nonce and before/after occurrence baselines,
      // so a fresh-chat UI transition is unnecessary and can introduce composer drift.
      const beforeBody=await this.bodyText();
      const beforeAssistant=await this.assistantText();
      const baselineBody=count(beforeBody,expectedText);
      const baselineAssistant=count(beforeAssistant,expectedText);
      const prompt=`${requestMarker}\nReply EXACTLY with the token below. Do not add punctuation, markdown or explanation.\n${expectedText}`;
      const submitMethod=await this.submitMetaExact(prompt,requestMarker);
      const deadline=Date.now()+(options.timeoutMs||this.config.timeoutMs||180000);
      let stable=0,lastCount=-1;
      while(Date.now()<deadline){
        if(await this.metaLoginGate())throw new Error('BLOCKED:META_LOGIN_REQUIRED');
        const s=await this.uiState();
        if(s.blockedBy)throw new Error(`BLOCKED:${s.blockedBy}`);
        const assistant=await this.assistantText();
        const assistantProof=count(assistant,expectedText)>baselineAssistant;
        const body=await this.bodyText();
        const bodyCount=count(body,expectedText);
        const bodyProof=bodyCount>=baselineBody+2;
        if((assistantProof||bodyProof)&&!s.stop){
          if(bodyCount===lastCount)stable++;else{lastCount=bodyCount;stable=1;}
          if(stable>=2&&await this.waitIdle(30000)){
            return {status:'ok',text:expectedText,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,url:s.href,fresh_chat:false,fresh_policy:'nonce-baseline-no-reset',submit_method:submitMethod,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started,capture:assistantProof?'assistant-container-exact-token':'body-occurrence-exact-token'}};
          }
        }
        await sleep(650);
      }
      throw new Error('META_EXACT_TOKEN_TIMEOUT');
    }catch(e){
      const blocked=/^BLOCKED:/.test(e.message);
      return {status:blocked?'blocked':'error',text:e.message,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started}};
    }
  }
}
