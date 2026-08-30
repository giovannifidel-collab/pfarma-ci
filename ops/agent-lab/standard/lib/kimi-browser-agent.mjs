import { KeyboardBrowserAgent } from './keyboard-browser-agent.mjs';

const sleep=ms=>new Promise(r=>setTimeout(r,ms));

export class KimiBrowserAgent extends KeyboardBrowserAgent {
  async clickKimiSendCandidate(){
    return this.eval(`(()=>{
      const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const controls=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);
      const composer=controls.find(e=>/kimi|message|chat|send/i.test(String(e.getAttribute('aria-label')||e.getAttribute('placeholder')||'')))||controls.find(e=>e.tagName==='TEXTAREA')||controls.find(e=>e.getAttribute('contenteditable')==='true')||controls.find(e=>e.getAttribute('role')==='textbox')||null;
      if(!composer)return {clicked:false,reason:'no-composer'};
      const candidates=[];
      let node=composer;
      for(let depth=0;depth<6&&node;depth++,node=node.parentElement){
        for(const b of node.querySelectorAll?.('button,[role="button"],input[type="submit"]')||[]){
          if(!visible(b)||b.disabled||b.getAttribute('aria-disabled')==='true')continue;
          const label=String(b.getAttribute('aria-label')||b.getAttribute('title')||b.innerText||b.textContent||'').trim();
          let score=0;
          if(/^send$/i.test(label)||/send message|submit|发送|發送/i.test(label))score+=100;
          if(String(b.getAttribute('type')||'').toLowerCase()==='submit')score+=80;
          if(b.querySelector('svg'))score+=10;
          score+=Math.max(0,20-depth*3);
          candidates.push({b,score,label,depth});
        }
      }
      candidates.sort((a,b)=>b.score-a.score);
      const hit=candidates[0];
      if(!hit)return {clicked:false,reason:'no-button'};
      hit.b.click();
      return {clicked:true,label:hit.label,score:hit.score,depth:hit.depth};
    })()`);
  }

  async dispatchDomEnter(){
    return this.eval(`(()=>{
      const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const controls=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);
      const e=controls.find(x=>/kimi|message|chat|send/i.test(String(x.getAttribute('aria-label')||x.getAttribute('placeholder')||'')))||controls.find(x=>x.tagName==='TEXTAREA')||controls.find(x=>x.getAttribute('contenteditable')==='true')||controls.find(x=>x.getAttribute('role')==='textbox')||null;
      if(!e)return false;e.focus();
      for(const type of ['keydown','keypress','keyup'])e.dispatchEvent(new KeyboardEvent(type,{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true,composed:true}));
      return true;
    })()`);
  }

  async submitPrompt(prompt,requestMarker){
    if(!await this.waitIdle())throw new Error('NOT_IDLE_BEFORE_SEND');
    await this.setComposer(prompt);
    const attempts=[];

    const ready=await this.waitSubmitReady(5000);
    if(ready&&await this.clickSubmit()){
      attempts.push('named-button');
      if(await this.verifySubmitted(requestMarker,6000))return 'named-button';
    }

    const candidate=await this.clickKimiSendCandidate().catch(()=>null);
    if(candidate?.clicked){
      attempts.push(`candidate:${candidate.label||candidate.score}`);
      if(await this.verifySubmitted(requestMarker,7000))return 'candidate-button';
    }

    if(await this.pressEnter()){
      attempts.push('cdp-enter');
      if(await this.verifySubmitted(requestMarker,7000))return 'cdp-enter';
    }

    if(await this.dispatchDomEnter()){
      attempts.push('dom-enter');
      if(await this.verifySubmitted(requestMarker,7000))return 'dom-enter';
    }

    const diag=await this.eval(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};return [...document.querySelectorAll('button,[role="button"],input[type="submit"]')].filter(visible).slice(-20).map(e=>({label:String(e.getAttribute('aria-label')||e.getAttribute('title')||e.innerText||e.textContent||'').trim().slice(0,120),type:e.getAttribute('type'),disabled:!!e.disabled,ariaDisabled:e.getAttribute('aria-disabled')}));})()`).catch(()=>[]);
    throw new Error(`KIMI_PROMPT_NOT_SUBMITTED:${attempts.join('+')||'none'}:BUTTONS=${JSON.stringify(diag)}`);
  }
}
