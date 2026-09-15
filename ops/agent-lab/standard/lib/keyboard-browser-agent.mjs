import { BrowserAgent } from './browser-agent.mjs';

const sleep=ms=>new Promise(r=>setTimeout(r,ms));

export class KeyboardBrowserAgent extends BrowserAgent{
  async activeComposerText(){
    return this.eval(`(()=>{
      const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const read=e=>String(e?.value||e?.innerText||e?.textContent||'');
      const a=document.activeElement;
      if(visible(a)&&(a.matches?.('textarea,input,[contenteditable="true"],[role="textbox"]')))return read(a);
      const pats=${this.patternsJs(this.config.composerPatterns)};
      const norm=e=>String(e?.getAttribute?.('aria-label')||e?.getAttribute?.('placeholder')||e?.innerText||e?.textContent||'').trim();
      const match=t=>pats.some(p=>{try{return new RegExp(p,'i').test(t)}catch{return false}});
      const all=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);
      let e=all.find(x=>match(norm(x)));
      if(!e&&${JSON.stringify(this.id)}==='perplexity')e=all.find(x=>x.getAttribute('contenteditable')==='true')||all[all.length-1]||null;
      if(!e&&${JSON.stringify(this.id)}==='meta')e=all.find(x=>x.getAttribute('contenteditable')==='true'&&x.getAttribute('role')==='textbox')||all.find(x=>x.getAttribute('contenteditable')==='true')||null;
      if(!e)e=all.find(x=>x.tagName==='TEXTAREA')||all.find(x=>x.getAttribute('contenteditable')==='true')||all.find(x=>x.getAttribute('role')==='textbox')||null;
      return read(e);
    })()`).catch(()=> '');
  }

  async setComposer(text){
    const info=await this.findComposerInfo();
    if(!info)throw new Error('COMPOSER_NOT_FOUND');
    const probe=text.slice(0,Math.min(36,text.length));

    const verify=async()=>{
      await sleep(350);
      const actual=await this.activeComposerText();
      return actual.includes(probe);
    };

    // Primary path: trusted CDP keyboard input. This is the same route used by
    // the successful standalone provider certifications.
    await this.call('Input.dispatchKeyEvent',{type:'rawKeyDown',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
    await this.call('Input.dispatchKeyEvent',{type:'keyUp',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
    await this.call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
    await this.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
    await this.call('Input.insertText',{text});
    if(await verify())return this.uiState();

    // Recovery for React/ProseMirror/contenteditable variants. Provider-specific
    // selection mirrors the already-certified Perplexity and Meta smoke paths.
    const payload=JSON.stringify(text);
    const ok=await this.eval(`(()=>{
      const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const pats=${this.patternsJs(this.config.composerPatterns)};
      const norm=e=>String(e?.getAttribute?.('aria-label')||e?.getAttribute?.('placeholder')||e?.innerText||e?.textContent||'').trim();
      const match=t=>pats.some(p=>{try{return new RegExp(p,'i').test(t)}catch{return false}});
      const all=[...document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')].filter(visible);
      let e=all.find(x=>match(norm(x)));
      const id=${JSON.stringify(this.id)};
      if(!e&&id==='perplexity')e=all.find(x=>x.getAttribute('contenteditable')==='true')||all[all.length-1]||null;
      if(!e&&id==='meta')e=all.find(x=>x.getAttribute('contenteditable')==='true'&&x.getAttribute('role')==='textbox')||all.find(x=>x.getAttribute('contenteditable')==='true')||null;
      if(!e)e=all.find(x=>x.tagName==='TEXTAREA')||all.find(x=>x.getAttribute('contenteditable')==='true')||all.find(x=>x.getAttribute('role')==='textbox')||null;
      if(!e)return false;
      e.focus();
      if(e.tagName==='TEXTAREA'||e.tagName==='INPUT'){
        let proto=e,d=null;
        while(proto&&!d){proto=Object.getPrototypeOf(proto);if(proto)d=Object.getOwnPropertyDescriptor(proto,'value')}
        if(d?.set)d.set.call(e,${payload});else e.value=${payload};
      }else{
        try{
          const sel=getSelection();sel?.removeAllRanges();
          const range=document.createRange();range.selectNodeContents(e);range.collapse(false);sel?.addRange(range);
        }catch{}
        try{document.execCommand('selectAll',false,null)}catch{}
        try{document.execCommand('insertText',false,${payload})}catch{e.textContent=${payload}}
        if(!String(e.innerText||e.textContent||'').includes(${JSON.stringify(text.slice(0,36))}))e.textContent=${payload};
      }
      try{e.dispatchEvent(new InputEvent('beforeinput',{bubbles:true,inputType:'insertText',data:${payload}}))}catch{}
      try{e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:${payload}}))}catch{e.dispatchEvent(new Event('input',{bubbles:true}))}
      e.dispatchEvent(new Event('change',{bubbles:true}));
      return true;
    })()`);
    if(!ok)throw new Error('COMPOSER_RECOVERY_SET_FAILED');
    if(!await verify())throw new Error('COMPOSER_TEXT_NOT_SET');
    return this.uiState();
  }
}
