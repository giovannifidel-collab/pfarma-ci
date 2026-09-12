import { BrowserAgent } from './browser-agent.mjs';

const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const count=(text,token)=>token?String(text||'').split(token).length-1:0;

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

  async run(task,options={}){
    const expectedText=options.expectedText?String(options.expectedText):null;
    if(!expectedText)return super.run(task,options);

    const started=Date.now();
    try{
      await this.connect();
      const hs=await this.waitComposer(30000);
      if(hs.blockedBy){
        return {status:'blocked',text:`blocked:${hs.blockedBy}`,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,url:hs.href,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started}};
      }

      const fresh=options.fresh??this.fresh;
      const freshOpened=fresh?await this.freshChat():false;
      const before=count(await this.bodyText(),expectedText);
      const submitMethod=await this.submitPrompt(String(task),expectedText);
      const timeout=options.timeoutMs||this.config.timeoutMs||180000;
      const deadline=Date.now()+timeout;
      let last=-1;
      let stable=0;

      while(Date.now()<deadline){
        const s=await this.uiState();
        if(s.blockedBy)throw new Error(`BLOCKED:${s.blockedBy}`);
        const body=await this.bodyText();
        const n=count(body,expectedText);
        if(n>=before+2){
          if(n===last)stable++;else stable=1;
          last=n;
          if(stable>=2&&!s.stop&&await this.waitIdle(20000)){
            const finalState=await this.uiState();
            return {
              status:'ok',
              text:expectedText,
              metadata:{
                agent_id:this.id,
                provider:this.config.product,
                port:this.port,
                url:finalState.href,
                fresh_chat:freshOpened,
                submit_method:submitMethod,
                response_proof:'body-occurrence-exact-token+stable',
                exact_token_occurrences:n-before,
                transport:'browser-cdp',
                zero_cost_path:true,
                latency_ms:Date.now()-started
              }
            };
          }
        }else{
          last=n;
          stable=0;
        }
        await sleep(650);
      }

      throw new Error('DUCK_EXACT_RESPONSE_TIMEOUT');
    }catch(e){
      const blocked=/^BLOCKED:/.test(e.message);
      return {status:blocked?'blocked':'error',text:e.message,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started}};
    }
  }
}
