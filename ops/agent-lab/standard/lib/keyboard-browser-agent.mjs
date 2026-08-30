import { BrowserAgent } from './browser-agent.mjs';

const sleep=ms=>new Promise(r=>setTimeout(r,ms));

export class KeyboardBrowserAgent extends BrowserAgent{
  async setComposer(text){
    const info=await this.findComposerInfo();
    if(!info)throw new Error('COMPOSER_NOT_FOUND');
    await this.call('Input.dispatchKeyEvent',{type:'rawKeyDown',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
    await this.call('Input.dispatchKeyEvent',{type:'keyUp',modifiers:2,key:'a',code:'KeyA',windowsVirtualKeyCode:65});
    await this.call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
    await this.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
    await this.call('Input.insertText',{text});
    await sleep(350);
    const s=await this.uiState();
    if(!s.composerText.includes(text.slice(0,Math.min(36,text.length))))throw new Error('COMPOSER_TEXT_NOT_SET');
    return s;
  }
}
