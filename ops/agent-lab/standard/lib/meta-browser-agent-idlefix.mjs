import { MetaBrowserAgent as BaseMetaBrowserAgent } from './meta-browser-agent.mjs';

const sleep=ms=>new Promise(r=>setTimeout(r,ms));

export class MetaBrowserAgent extends BaseMetaBrowserAgent {
  async metaUiState(){
    const s=await super.metaUiState();
    return {...s,generating:!!(s.stopVisible&&!s.stopDisabled)};
  }

  async clickMetaNewChat(){
    const p=await this.eval(`(()=>{const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const e=document.querySelector('[data-testid="new-chat-button"]');if(!e||!visible(e)||e.disabled||e.getAttribute('aria-disabled')==='true')return null;const r=e.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()`);
    if(!p)return false;
    await this.call('Input.dispatchMouseEvent',{type:'mouseMoved',x:p.x,y:p.y,button:'none'});
    await this.call('Input.dispatchMouseEvent',{type:'mousePressed',x:p.x,y:p.y,button:'left',clickCount:1});
    await this.call('Input.dispatchMouseEvent',{type:'mouseReleased',x:p.x,y:p.y,button:'left',clickCount:1});
    await sleep(1400);
    return true;
  }

  async metaWaitIdle(timeout=60000){
    const deadline=Date.now()+timeout;
    let stable=0,busySince=0,stopAttempted=false,newChatAttempted=false,targetReset=false,missingSince=0;
    while(Date.now()<deadline){
      const s=await this.metaUiState();
      if(s.loginVisible)throw new Error('BLOCKED:META_LOGIN_REQUIRED');
      if(s.composer&&!s.generating){
        stable++;
        busySince=0;
        missingSince=0;
        if(stable>=4)return true;
      }else{
        stable=0;
        if(s.generating){
          missingSince=0;
          if(!busySince)busySince=Date.now();
          const stuckFor=Date.now()-busySince;
          if(!stopAttempted&&stuckFor>=4000){
            stopAttempted=true;
            if(await this.clickMetaStop().catch(()=>false)){
              await sleep(1200);
              continue;
            }
          }
          if(!newChatAttempted&&stuckFor>=9000){
            newChatAttempted=true;
            if(await this.clickMetaNewChat().catch(()=>false)){
              await this.metaWaitComposer(20000,{repair:true});
              busySince=0;
              stopAttempted=false;
              await sleep(600);
              continue;
            }
          }
          if(!targetReset&&stuckFor>=18000){
            targetReset=true;
            await this.resetIdleTarget();
            busySince=0;
            stopAttempted=false;
            newChatAttempted=false;
            await sleep(800);
            continue;
          }
        }else if(!s.composer){
          if(!missingSince)missingSince=Date.now();
          if(!newChatAttempted&&Date.now()-missingSince>=5000){
            newChatAttempted=true;
            if(await this.clickMetaNewChat().catch(()=>false)){
              await this.metaWaitComposer(20000,{repair:true});
              missingSince=0;
              continue;
            }
          }
          if(!targetReset&&Date.now()-missingSince>=12000){
            targetReset=true;
            await this.resetIdleTarget();
            missingSince=0;
            continue;
          }
        }
      }
      await sleep(350);
    }
    return false;
  }
}
