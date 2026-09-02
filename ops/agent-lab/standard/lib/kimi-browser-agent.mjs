import { KeyboardBrowserAgent } from './keyboard-browser-agent.mjs';

const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const retryableCdpError=e=>/CDP_TIMEOUT_(Runtime\.enable|Runtime\.evaluate|Page\.enable)|CDP_CONNECT_(TIMEOUT|ERROR)|PAGE_WEBSOCKET_NOT_FOUND|WebSocket|InvalidStateError/i.test(String(e?.message||e||''));

export class KimiBrowserAgent extends KeyboardBrowserAgent {
  async ensureBrowser(){
    const fallback=await super.ensureBrowser();
    try{
      const list=await (await fetch(`http://127.0.0.1:${this.port}/json/list`,{signal:AbortSignal.timeout(3000)})).json();
      const preferred=list.find(t=>t?.type==='page'&&/https?:\/\/[^/]*kimi\.ai/i.test(String(t.url||''))&&t.webSocketDebuggerUrl);
      return preferred||fallback;
    }catch{return fallback;}
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

  async clickKimiSendCandidate(){
    return this.eval(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const controls=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);const composer=controls.find(e=>/kimi|message|chat|send/i.test(String(e.getAttribute('aria-label')||e.getAttribute('placeholder')||'')))||controls.find(e=>e.tagName==='TEXTAREA')||controls.find(e=>e.getAttribute('contenteditable')==='true')||controls.find(e=>e.getAttribute('role')==='textbox')||null;if(!composer)return {clicked:false,reason:'no-composer'};const cr=composer.getBoundingClientRect();const candidates=[];let node=composer;for(let depth=0;depth<7&&node;depth++,node=node.parentElement){for(const b of node.querySelectorAll?.('button,[role="button"],input[type="submit"]')||[]){if(!visible(b)||b.disabled||b.getAttribute('aria-disabled')==='true')continue;const label=String(b.getAttribute('aria-label')||b.getAttribute('title')||b.innerText||b.textContent||'').trim();const r=b.getBoundingClientRect();let score=0;if(/^send$/i.test(label)||/send message|submit|发送|發送|arrow.*up/i.test(label))score+=160;if(String(b.getAttribute('type')||'').toLowerCase()==='submit')score+=120;if(b.querySelector('svg'))score+=15;if(r.left>=cr.left+cr.width*0.55)score+=35;if(Math.abs((r.top+r.height/2)-(cr.top+cr.height/2))<Math.max(60,cr.height))score+=20;score+=Math.max(0,24-depth*3);if(/attach|upload|file|voice|microphone|mic|image|tool|model/i.test(label))score-=120;candidates.push({b,score,label,depth});}}candidates.sort((a,b)=>b.score-a.score);const hit=candidates[0];if(!hit||hit.score<0)return {clicked:false,reason:'no-safe-button'};hit.b.click();return {clicked:true,label:hit.label,score:hit.score,depth:hit.depth};})()`);
  }

  async dispatchDomEnter(){
    return this.eval(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const controls=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);const e=controls.find(x=>/kimi|message|chat|send/i.test(String(x.getAttribute('aria-label')||x.getAttribute('placeholder')||'')))||controls.find(x=>x.tagName==='TEXTAREA')||controls.find(x=>x.getAttribute('contenteditable')==='true')||controls.find(x=>x.getAttribute('role')==='textbox')||null;if(!e)return false;e.focus();for(const type of ['keydown','keypress','keyup'])e.dispatchEvent(new KeyboardEvent(type,{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true,composed:true}));return true;})()`);
  }

  async submitPrompt(prompt,requestMarker){
    if(!await this.waitIdle())throw new Error('NOT_IDLE_BEFORE_SEND');
    await this.setComposer(prompt);
    const attempts=[];
    if(await this.pressEnter()){
      attempts.push('cdp-enter-first');
      if(await this.verifySubmitted(requestMarker,10000))return 'cdp-enter-first';
    }
    const current=await this.activeComposerText().catch(()=> '');
    if(current.includes(requestMarker))await this.setComposer(prompt);
    const ready=await this.waitSubmitReady(5000);
    if(ready&&await this.clickSubmit()){
      attempts.push('named-button');
      if(await this.verifySubmitted(requestMarker,8000))return 'named-button';
    }
    const candidate=await this.clickKimiSendCandidate().catch(()=>null);
    if(candidate?.clicked){attempts.push(`candidate:${candidate.label||candidate.score}`);if(await this.verifySubmitted(requestMarker,10000))return 'candidate-button';}
    if(await this.submitNearestForm()){attempts.push('nearest-form');if(await this.verifySubmitted(requestMarker,9000))return 'nearest-form';}
    if(await this.dispatchDomEnter()){attempts.push('dom-enter');if(await this.verifySubmitted(requestMarker,9000))return 'dom-enter';}
    throw new Error(`KIMI_PROMPT_NOT_SUBMITTED:${attempts.join('+')||'none'}`);
  }
}
