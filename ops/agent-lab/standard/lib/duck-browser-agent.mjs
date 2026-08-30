import { BrowserAgent } from './browser-agent.mjs';

const sleep=ms=>new Promise(r=>setTimeout(r,ms));

export class DuckBrowserAgent extends BrowserAgent {
  async dismissTips(){
    return this.eval(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const e=[...document.querySelectorAll('button,[role="button"]')].filter(visible).find(x=>/^got it!?$/i.test(String(x.innerText||x.getAttribute('aria-label')||'').trim()));if(!e)return false;e.click();return true;})()`).catch(()=>false);
  }

  async freshChat(){
    await this.dismissTips();
    const clicked=await this.eval(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const els=[...document.querySelectorAll('button,a,[role="button"]')].filter(visible);const e=els.find(x=>/^new chat(?:\\s|$)/i.test(String(x.innerText||x.getAttribute('aria-label')||'').trim()));if(!e)return false;e.click();return true;})()`).catch(()=>false);
    if(clicked){await sleep(1200);await this.waitComposer(30000);}
    return clicked;
  }

  async waitDuckSendReady(timeout=10000){
    const deadline=Date.now()+timeout;
    while(Date.now()<deadline){
      const s=await this.eval(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const actions=[...document.querySelectorAll('button,[role="button"],input[type="submit"]')].filter(visible);const e=actions.find(x=>/^send$/i.test(String(x.getAttribute('aria-label')||x.innerText||x.value||'').trim()))||actions.find(x=>x.tagName==='BUTTON'&&String(x.getAttribute('type')||'').toLowerCase()==='submit');return e?{ready:!e.disabled&&e.getAttribute('aria-disabled')!=='true',aria:e.getAttribute('aria-label'),type:e.getAttribute('type')}:null;})()`);
      if(s?.ready)return s;
      await sleep(200);
    }
    return null;
  }

  async clickDuckSend(){
    return this.eval(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const actions=[...document.querySelectorAll('button,[role="button"],input[type="submit"]')].filter(visible);const e=actions.find(x=>/^send$/i.test(String(x.getAttribute('aria-label')||x.innerText||x.value||'').trim()))||actions.find(x=>x.tagName==='BUTTON'&&String(x.getAttribute('type')||'').toLowerCase()==='submit');if(!e||e.disabled||e.getAttribute('aria-disabled')==='true')return false;e.click();return true;})()`);
  }

  async submitPrompt(prompt,requestMarker){
    if(!await this.waitIdle())throw new Error('NOT_IDLE_BEFORE_SEND');
    await this.dismissTips();
    await this.setComposer(prompt);
    const ready=await this.waitDuckSendReady(12000);
    if(!ready)throw new Error('DUCK_SEND_NOT_READY');
    if(!await this.clickDuckSend())throw new Error('DUCK_SEND_CLICK_FAILED');
    if(!await this.verifySubmitted(requestMarker,15000))throw new Error('DUCK_PROMPT_NOT_SUBMITTED');
    return 'send-button-certified-path';
  }
}
