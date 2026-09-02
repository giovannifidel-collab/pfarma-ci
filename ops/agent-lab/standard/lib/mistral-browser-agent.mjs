import { KeyboardBrowserAgent } from './keyboard-browser-agent.mjs';

const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const count=(text,token)=>token?String(text||'').split(token).length-1:0;

export class MistralBrowserAgent extends KeyboardBrowserAgent {
  async mistralComposer(){
    return this.eval(`(()=>{const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const all=[...document.querySelectorAll('[contenteditable="true"],textarea')].filter(visible);const e=all.find(x=>x.getAttribute('contenteditable')==='true')||all[all.length-1]||null;if(!e)return null;e.focus();return {tag:e.tagName.toLowerCase(),text:String(e.innerText||e.value||'')};})()`);
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
      await this.call('Input.dispatchKeyEvent',{type:'rawKeyDown',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
      await this.call('Input.dispatchKeyEvent',{type:'keyUp',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
      await this.call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
      await this.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
      await this.call('Input.insertText',{text:String(task)});
      await sleep(400);
      const inserted=await this.mistralComposer();
      if(!inserted?.text?.includes(expectedText))throw new Error('MISTRAL_TEXT_NOT_INSERTED');
      await this.call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
      await this.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
      const deadline=Date.now()+(options.timeoutMs||this.config.timeoutMs||150000);
      while(Date.now()<deadline){
        const body=await this.bodyText();
        if(count(body,expectedText)>=before+2){
          return {status:'ok',text:expectedText,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started,response_proof:'mistral-body-occurrence-exact-token'}};
        }
        const low=String(body).toLowerCase();
        if(low.includes('sign in')&&low.includes('sign up')&&!low.includes('default workspace'))return {status:'blocked',text:'blocked:MISTRAL_LOGIN_REQUIRED',metadata:{agent_id:this.id,port:this.port}};
        await sleep(700);
      }
      throw new Error('MISTRAL_EXACT_RESPONSE_TIMEOUT');
    }catch(e){return {status:/^blocked:/i.test(e.message)?'blocked':'error',text:e.message,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started}};}
  }
}
