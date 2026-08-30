import { BrowserAgent } from './browser-agent.mjs';

const sleep=ms=>new Promise(r=>setTimeout(r,ms));

export class KeyboardBrowserAgent extends BrowserAgent{
  async setComposer(text){
    const info=await this.findComposerInfo();
    if(!info)throw new Error('COMPOSER_NOT_FOUND');

    const verify=async()=>{
      await sleep(300);
      const s=await this.uiState();
      return s.composerText.includes(text.slice(0,Math.min(36,text.length))) ? s : null;
    };

    // Primary path: trusted CDP keyboard input. This matches the route used by
    // the successful standalone certifications for most browser providers.
    await this.call('Input.dispatchKeyEvent',{type:'rawKeyDown',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
    await this.call('Input.dispatchKeyEvent',{type:'keyUp',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
    await this.call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
    await this.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
    await this.call('Input.insertText',{text});
    let s=await verify();
    if(s)return s;

    // Recovery path for React/ProseMirror/contenteditable composers (notably
    // Perplexity/Meta UI variants) where Input.insertText can hit a wrapper.
    const payload=JSON.stringify(text);
    const ok=await this.eval(`(()=>{
      const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const pats=${this.patternsJs(this.config.composerPatterns)};
      const norm=e=>String(e?.getAttribute?.('aria-label')||e?.getAttribute?.('placeholder')||e?.innerText||e?.textContent||'').trim();
      const match=t=>pats.some(p=>{try{return new RegExp(p,'i').test(t)}catch{return false}});
      const all=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);
      const e=all.find(x=>match(norm(x)))||all.find(x=>x.tagName==='TEXTAREA')||all.find(x=>x.getAttribute('contenteditable')==='true')||all.find(x=>x.getAttribute('role')==='textbox')||null;
      if(!e)return false;
      e.focus();
      if(e.tagName==='TEXTAREA'||e.tagName==='INPUT'){
        let proto=e,d=null;
        while(proto&&!d){proto=Object.getPrototypeOf(proto);if(proto)d=Object.getOwnPropertyDescriptor(proto,'value')}
        if(d?.set)d.set.call(e,${payload});else e.value=${payload};
      }else{
        const sel=getSelection();
        try{sel?.removeAllRanges()}catch{}
        e.textContent='';
        try{document.execCommand('insertText',false,${payload})}catch{e.textContent=${payload}}
        if(!String(e.innerText||e.textContent||'').includes(${JSON.stringify(text.slice(0,36))}))e.textContent=${payload};
      }
      try{e.dispatchEvent(new InputEvent('beforeinput',{bubbles:true,inputType:'insertText',data:${payload}}))}catch{}
      try{e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:${payload}}))}catch{e.dispatchEvent(new Event('input',{bubbles:true}))}
      e.dispatchEvent(new Event('change',{bubbles:true}));
      return true;
    })()`);
    if(!ok)throw new Error('COMPOSER_RECOVERY_SET_FAILED');
    s=await verify();
    if(!s)throw new Error('COMPOSER_TEXT_NOT_SET');
    return s;
  }
}
