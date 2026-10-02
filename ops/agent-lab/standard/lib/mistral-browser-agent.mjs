import { KeyboardBrowserAgent } from './keyboard-browser-agent.mjs';

const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const count=(text,token)=>token?String(text||'').split(token).length-1:0;

export class MistralBrowserAgent extends KeyboardBrowserAgent {
  async mistralComposer(){
    return this.eval(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const all=[...document.querySelectorAll('[contenteditable="true"],textarea,input[type="text"]')].filter(visible);const e=all.find(x=>x.getAttribute('contenteditable')==='true')||all.find(x=>x.tagName==='TEXTAREA')||all[all.length-1]||null;if(!e)return null;e.focus();return {tag:e.tagName.toLowerCase(),text:String(e.value||e.innerText||e.textContent||'')};})()`);
  }

  async setMistralInput(text){
    const value=String(text);
    const payload=JSON.stringify(value);
    const probe=JSON.stringify(value.slice(0,Math.min(36,value.length)));
    const ok=await this.eval(`(()=>{
      const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const all=[...document.querySelectorAll('[contenteditable="true"],textarea,input[type="text"]')].filter(visible);
      const e=all.find(x=>x.getAttribute('contenteditable')==='true')||all.find(x=>x.tagName==='TEXTAREA')||all[all.length-1]||null;
      if(!e)return false;
      e.focus();
      if(e.tagName==='TEXTAREA'||e.tagName==='INPUT'){
        let proto=e,d=null;
        while(proto&&!d){proto=Object.getPrototypeOf(proto);if(proto)d=Object.getOwnPropertyDescriptor(proto,'value')}
        if(d?.set)d.set.call(e,${payload});else e.value=${payload};
        try{e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:${payload}}))}catch{e.dispatchEvent(new Event('input',{bubbles:true}))}
        e.dispatchEvent(new Event('change',{bubbles:true}));
      }else{
        try{
          const sel=getSelection(),range=document.createRange();
          range.selectNodeContents(e);sel.removeAllRanges();sel.addRange(range);
          document.execCommand('delete',false,null);
          document.execCommand('insertText',false,${payload});
        }catch{return false}
        try{e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:${payload}}))}catch{e.dispatchEvent(new Event('input',{bubbles:true}))}
      }
      return String(e.value||e.innerText||e.textContent||'').includes(${probe});
    })()`).catch(()=>false);
    if(!ok)await super.setComposer(value);
    await sleep(400);
    const inserted=await this.mistralComposer();
    if(!inserted?.text?.includes(value.slice(0,Math.min(36,value.length))))throw new Error('MISTRAL_TEXT_NOT_INSERTED');
    return inserted;
  }

  async submitMistral(marker){
    const ready=await this.waitSubmitReady(6000).catch(()=>null);
    if(ready&&await this.clickSubmit().catch(()=>false)){
      if(await this.verifySubmitted(marker,7000).catch(()=>false))return 'button';
    }
    if(await this.pressEnter().catch(()=>false)){
      if(await this.verifySubmitted(marker,7000).catch(()=>false))return 'enter';
    }
    throw new Error('MISTRAL_PROMPT_NOT_SUBMITTED');
  }

  async run(task,options={}){
    const expectedText=options.expectedText?String(options.expectedText):null;
    if(!expectedText)return super.run(task,options);
    const started=Date.now();
    try{
      await this.connect();
      let composer=null;const readyDeadline=Date.now()+45000;
      while(Date.now()<readyDeadline){composer=await this.mistralComposer();if(composer)break;await sleep(400);}
      if(!composer)throw new Error('MISTRAL_COMPOSER_NOT_READY');
      const before=count(await this.bodyText(),expectedText);
      await this.setMistralInput(String(task));
      const submitMethod=await this.submitMistral(expectedText);
      const deadline=Date.now()+(options.timeoutMs||this.config.timeoutMs||150000);
      while(Date.now()<deadline){
        const body=await this.bodyText();
        if(count(body,expectedText)>=before+2){
          return {status:'ok',text:expectedText,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started,response_proof:'mistral-body-occurrence-exact-token',submit_method:submitMethod}};
        }
        const low=String(body).toLowerCase();
        if(low.includes('sign in')&&low.includes('sign up')&&!low.includes('default workspace'))return {status:'blocked',text:'blocked:MISTRAL_LOGIN_REQUIRED',metadata:{agent_id:this.id,port:this.port}};
        await sleep(700);
      }
      throw new Error('MISTRAL_EXACT_RESPONSE_TIMEOUT');
    }catch(e){return {status:/^blocked:/i.test(e.message)?'blocked':'error',text:e.message,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started}};}
  }
}
