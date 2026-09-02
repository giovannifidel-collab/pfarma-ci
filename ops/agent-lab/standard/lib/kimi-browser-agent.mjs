import { KeyboardBrowserAgent } from './keyboard-browser-agent.mjs';

const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const retryableCdpError=e=>/CDP_TIMEOUT_(Runtime\.enable|Runtime\.evaluate|Page\.enable)|CDP_CONNECT_(TIMEOUT|ERROR)|PAGE_WEBSOCKET_NOT_FOUND|WebSocket|InvalidStateError/i.test(String(e?.message||e||''));

export class KimiBrowserAgent extends KeyboardBrowserAgent {
  async ensureBrowser(){
    const fallback=await super.ensureBrowser();
    try{
      const base=`http://127.0.0.1:${this.port}`;
      const list=await (await fetch(`${base}/json/list`,{signal:AbortSignal.timeout(3000)})).json();
      const preferred=list.find(t=>t?.type==='page'&&/https?:\/\/[^/]*kimi\.ai/i.test(String(t.url||''))&&t.webSocketDebuggerUrl);
      if(preferred)return preferred;
      const opened=await fetch(`${base}/json/new?${encodeURIComponent('https://www.kimi.ai/')}`,{method:'PUT',signal:AbortSignal.timeout(7000)}).catch(()=>null);
      if(opened?.ok){
        const target=await opened.json();
        if(target?.webSocketDebuggerUrl){await sleep(1200);return target;}
      }
    }catch{}
    return fallback;
  }

  async recycleTarget(){
    const port=this.port||this.config.port;
    const base=`http://127.0.0.1:${port}`;
    this.close();
    try{
      const response=await fetch(`${base}/json/list`,{signal:AbortSignal.timeout(4000)});
      if(!response.ok)return false;
      const targets=await response.json();
      const matching=targets.filter(t=>t?.type==='page'&&this.config.targetPattern.test(String(t.url||'')));
      const preferred=matching.find(t=>/https?:\/\/[^/]*kimi\.ai/i.test(String(t.url||'')));
      const fallbackUrl=preferred?.url||'https://www.kimi.ai/';
      for(const target of matching){
        if(!target?.id)continue;
        await fetch(`${base}/json/close/${encodeURIComponent(target.id)}`,{signal:AbortSignal.timeout(4000)}).catch(()=>null);
      }
      await sleep(600);
      const opened=await fetch(`${base}/json/new?${encodeURIComponent(fallbackUrl)}`,{method:'PUT',signal:AbortSignal.timeout(7000)});
      if(!opened.ok)return false;
      const target=await opened.json();
      if(target?.id)await fetch(`${base}/json/activate/${encodeURIComponent(target.id)}`,{signal:AbortSignal.timeout(4000)}).catch(()=>null);
      await sleep(1800);
      return true;
    }catch{return false;}
  }

  async connect(){
    let last=null;
    for(let attempt=1;attempt<=3;attempt++){
      try{
        if(this.ws?.readyState===WebSocket.OPEN){
          await this.call('Runtime.evaluate',{expression:'1',returnByValue:true},6000);
          return;
        }
        await super.connect();
        await this.call('Runtime.evaluate',{expression:'1',returnByValue:true},7000);
        return;
      }catch(e){
        last=e;
        this.close();
        if(!retryableCdpError(e))throw e;
        await this.recycleTarget().catch(()=>false);
        await sleep(900*attempt);
      }
    }
    throw new Error(`KIMI_CDP_RECOVERY_EXHAUSTED:${String(last?.message||last||'unknown')}`);
  }

  async kimiUiState(){
    return this.eval(`(()=>{
      const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const editors=[...document.querySelectorAll('.chat-input-editor,[data-lexical-editor="true"],[contenteditable="true"]')].filter(visible);
      const editor=editors.find(e=>e.matches('.chat-input-editor')&&e.closest('.chat-editor'))||editors.find(e=>e.matches('.chat-input-editor'))||editors[editors.length-1]||null;
      const sends=[...document.querySelectorAll('.send-button-container')].filter(visible);
      const send=sends[sends.length-1]||null;
      const body=String(document.body?.innerText||'');
      const login=/log in to kimi|sign in to kimi|continue with\s+(google|apple|phone)|phone number/i.test(body)&&!editor;
      return {
        href:String(location.href||''),ready:document.readyState,composer:!!editor,
        composerText:editor?String(editor.textContent||editor.innerText||''):'',
        sendVisible:!!send,
        sendDisabled:send?send.classList.contains('disabled')||send.getAttribute('aria-disabled')==='true'||getComputedStyle(send).pointerEvents==='none':true,
        generating:!!send&&send.classList.contains('stop'),
        userCount:document.querySelectorAll('.segment.segment-user,.segment-user').length,
        assistantCount:document.querySelectorAll('.segment.segment-assistant,.segment-assistant').length,
        loginVisible:login
      };
    })()`);
  }

  async kimiWaitComposer(timeout=45000){
    const deadline=Date.now()+timeout;
    while(Date.now()<deadline){
      const s=await this.kimiUiState();
      if(s.loginVisible)throw new Error('BLOCKED:KIMI_LOGIN_REQUIRED');
      if(s.composer&&s.ready!=='loading')return s;
      await sleep(350);
    }
    throw new Error('KIMI_COMPOSER_NOT_READY');
  }

  async kimiWaitIdle(timeout=90000){
    const deadline=Date.now()+timeout;let stable=0;
    while(Date.now()<deadline){
      const s=await this.kimiUiState();
      if(s.loginVisible)throw new Error('BLOCKED:KIMI_LOGIN_REQUIRED');
      if(s.composer&&!s.generating){stable++;if(stable>=4)return true;}else stable=0;
      await sleep(300);
    }
    return false;
  }

  async kimiAssistantSnapshot(){
    return this.eval(`(()=>{
      const items=[...document.querySelectorAll('.segment.segment-assistant,.segment-assistant')];
      const item=items[items.length-1]||null;
      if(!item)return {count:0,text:'',decorated:false};
      const body=item.querySelector('.segment-content-box')||item.querySelector('.segment-content')||item;
      const clone=body.cloneNode(true);
      clone.querySelectorAll('.thinking-container').forEach(e=>e.remove());
      const decorated=!!clone.querySelector('.segment-code,pre,code,blockquote,ul,ol,h1,h2,h3,h4,h5,h6,strong,em');
      const text=String(clone.innerText||clone.textContent||'').trim();
      return {count:items.length,text,decorated};
    })()`);
  }

  async setKimiComposer(text){
    const payload=JSON.stringify(String(text));
    const probe=JSON.stringify(String(text).slice(0,Math.min(36,String(text).length)));
    const ok=await this.eval(`(()=>{
      const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const all=[...document.querySelectorAll('.chat-input-editor,[data-lexical-editor="true"]')].filter(visible);
      const e=all.find(x=>x.matches('.chat-input-editor')&&x.closest('.chat-editor'))||all.find(x=>x.matches('.chat-input-editor'))||all[all.length-1]||null;
      if(!e)return false;
      e.focus();
      try{
        const sel=getSelection();const range=document.createRange();range.selectNodeContents(e);sel.removeAllRanges();sel.addRange(range);
        document.execCommand('insertText',false,${payload});
      }catch{return false;}
      try{e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:${payload}}))}catch{e.dispatchEvent(new Event('input',{bubbles:true}))}
      return String(e.textContent||e.innerText||'').includes(${probe});
    })()`).catch(()=>false);
    if(!ok)await super.setComposer(text);
    await sleep(450);
    const s=await this.kimiUiState();
    if(!s.composerText.includes(String(text).slice(0,Math.min(36,String(text).length))))throw new Error('KIMI_TEXT_NOT_INSERTED');
    return s;
  }

  async clickKimiSend(){
    return this.eval(`(()=>{
      const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const all=[...document.querySelectorAll('.send-button-container')].filter(visible);
      const e=all[all.length-1]||null;
      if(!e||e.classList.contains('stop')||e.classList.contains('disabled')||e.getAttribute('aria-disabled')==='true'||getComputedStyle(e).pointerEvents==='none')return false;
      e.click();return true;
    })()`).catch(()=>false);
  }

  async verifyKimiSubmitted(marker,beforeUserCount,timeout=12000){
    const deadline=Date.now()+timeout;
    while(Date.now()<deadline){
      const s=await this.kimiUiState();
      if(s.loginVisible)throw new Error('BLOCKED:KIMI_LOGIN_REQUIRED');
      if(!s.composerText.includes(marker)&&(s.userCount>beforeUserCount||s.generating||s.composerText.trim()===''))return true;
      await sleep(250);
    }
    return false;
  }

  async clickKimiSendCandidate(){
    return this.eval(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const controls=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);const composer=controls.find(e=>/kimi|message|chat|send/i.test(String(e.getAttribute('aria-label')||e.getAttribute('placeholder')||'')))||controls.find(e=>e.tagName==='TEXTAREA')||controls.find(e=>e.getAttribute('contenteditable')==='true')||controls.find(e=>e.getAttribute('role')==='textbox')||null;if(!composer)return {clicked:false,reason:'no-composer'};const cr=composer.getBoundingClientRect();const candidates=[];let node=composer;for(let depth=0;depth<7&&node;depth++,node=node.parentElement){for(const b of node.querySelectorAll?.('button,[role="button"],input[type="submit"]')||[]){if(!visible(b)||b.disabled||b.getAttribute('aria-disabled')==='true')continue;const label=String(b.getAttribute('aria-label')||b.getAttribute('title')||b.innerText||b.textContent||'').trim();const r=b.getBoundingClientRect();let score=0;if(/^send$/i.test(label)||/send message|submit|发送|發送|arrow.*up/i.test(label))score+=160;if(String(b.getAttribute('type')||'').toLowerCase()==='submit')score+=120;if(b.querySelector('svg'))score+=15;if(r.left>=cr.left+cr.width*0.55)score+=35;if(Math.abs((r.top+r.height/2)-(cr.top+cr.height/2))<Math.max(60,cr.height))score+=20;score+=Math.max(0,24-depth*3);if(/attach|upload|file|voice|microphone|mic|image|tool|model/i.test(label))score-=120;candidates.push({b,score,label,depth});}}candidates.sort((a,b)=>b.score-a.score);const hit=candidates[0];if(!hit||hit.score<0)return {clicked:false,reason:'no-safe-button'};hit.b.click();return {clicked:true,label:hit.label,score:hit.score,depth:hit.depth};})()`);
  }

  async dispatchDomEnter(){
    return this.eval(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const controls=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);const e=controls.find(x=>x.matches('.chat-input-editor'))||controls.find(x=>/kimi|message|chat|send/i.test(String(x.getAttribute('aria-label')||x.getAttribute('placeholder')||'')))||controls.find(x=>x.getAttribute('contenteditable')==='true')||controls.find(x=>x.tagName==='TEXTAREA')||controls.find(x=>x.getAttribute('role')==='textbox')||null;if(!e)return false;e.focus();for(const type of ['keydown','keypress','keyup'])e.dispatchEvent(new KeyboardEvent(type,{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true,composed:true}));return true;})()`);
  }

  async submitPrompt(prompt,requestMarker){
    if(!await this.kimiWaitIdle())throw new Error('KIMI_NOT_IDLE_BEFORE_SEND');
    const before=(await this.kimiUiState()).userCount;
    await this.setKimiComposer(prompt);
    const attempts=[];
    const readyDeadline=Date.now()+7000;
    while(Date.now()<readyDeadline){
      const s=await this.kimiUiState();
      if(s.sendVisible&&!s.sendDisabled&&!s.generating)break;
      await sleep(200);
    }
    if(await this.clickKimiSend()){
      attempts.push('kimi-send-container');
      if(await this.verifyKimiSubmitted(requestMarker,before,12000))return 'kimi-send-container';
    }
    if(await this.pressEnter()){
      attempts.push('cdp-enter');
      if(await this.verifyKimiSubmitted(requestMarker,before,10000))return 'cdp-enter';
    }
    const current=await this.activeComposerText().catch(()=> '');
    if(current.includes(requestMarker))await this.setKimiComposer(prompt);
    const candidate=await this.clickKimiSendCandidate().catch(()=>null);
    if(candidate?.clicked){attempts.push(`candidate:${candidate.label||candidate.score}`);if(await this.verifyKimiSubmitted(requestMarker,before,10000))return 'candidate-button';}
    if(await this.submitNearestForm()){attempts.push('nearest-form');if(await this.verifyKimiSubmitted(requestMarker,before,9000))return 'nearest-form';}
    if(await this.dispatchDomEnter()){attempts.push('dom-enter');if(await this.verifyKimiSubmitted(requestMarker,before,9000))return 'dom-enter';}
    throw new Error(`KIMI_PROMPT_NOT_SUBMITTED:${attempts.join('+')||'none'}`);
  }

  async run(task,options={}){
    const expectedText=options.expectedText?String(options.expectedText):null;
    if(!expectedText)return super.run(task,options);
    const started=Date.now();
    const marker=`HIVE_KIMI_PROBE:${Date.now()}:${Math.random().toString(16).slice(2,10)}`;
    try{
      await this.connect();
      let state=await this.kimiWaitComposer(45000);
      if(!/https?:\/\/[^/]*kimi\.ai/i.test(state.href)){
        if(!await this.recycleTarget())throw new Error('KIMI_INTERNATIONAL_TARGET_UNAVAILABLE');
        await this.connect();
        state=await this.kimiWaitComposer(45000);
      }
      const before=await this.kimiAssistantSnapshot();
      const prompt=`${marker}\nReturn exactly this token and nothing else. Do not use markdown, quotes, punctuation or explanation:\n${expectedText}`;
      const submitMethod=await this.submitPrompt(prompt,marker);
      const deadline=Date.now()+(options.timeoutMs||this.config.timeoutMs||180000);
      let stableText=null,stable=0;
      while(Date.now()<deadline){
        const s=await this.kimiUiState();
        if(s.loginVisible)throw new Error('BLOCKED:KIMI_LOGIN_REQUIRED');
        const snap=await this.kimiAssistantSnapshot();
        if(snap.count>before.count&&snap.text&&!s.generating){
          if(snap.text===stableText)stable++;else{stableText=snap.text;stable=1;}
          if(stable>=3){
            if(snap.text===expectedText&&!snap.decorated){
              return {status:'ok',text:expectedText,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,url:s.href||state.href,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started,capture:'kimi-assistant-segment-exact',submit_method:submitMethod,assistant_delta:snap.count-before.count,fresh_chat:false,fresh_policy:'provider-segment-proof'}};
            }
            return {status:'error',text:'KIMI_EXACT_OUTPUT_MISMATCH',metadata:{agent_id:this.id,provider:this.config.product,port:this.port,url:s.href||state.href,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started,capture:'kimi-assistant-segment-mismatch',submit_method:submitMethod,assistant_delta:snap.count-before.count,response_length:snap.text.length,decorated:snap.decorated}};
          }
        }
        await sleep(650);
      }
      throw new Error('KIMI_EXACT_RESPONSE_TIMEOUT');
    }catch(e){
      const message=String(e?.message||e||'KIMI_RUN_ERROR');
      return {status:/^BLOCKED:/i.test(message)?'blocked':'error',text:message,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started}};
    }
  }

  async recover(reason='unknown'){
    this.close();
    const recycled=await this.recycleTarget().catch(()=>false);
    if(!recycled)return {recovered:false,method:'kimi-target-recycle',reason};
    try{
      await this.connect();
      await this.kimiWaitComposer(30000);
      return {recovered:true,method:'kimi-target-recycle',reason,port:this.port};
    }catch(e){
      this.close();
      return {recovered:false,method:'kimi-target-recycle',reason,error:String(e?.message||e)};
    }
  }
}
