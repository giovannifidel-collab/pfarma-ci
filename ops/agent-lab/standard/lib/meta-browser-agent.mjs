import { MarkerBrowserAgent } from './marker-browser-agent.mjs';

export class MetaBrowserAgent extends MarkerBrowserAgent {
  async run(task,options={}){
    const expectedText=options.expectedText?String(options.expectedText):null;
    if(!expectedText)return super.run(task,options);
    const started=Date.now();
    const requestMarker=`HIVE_META_PROBE:${Date.now()}`;
    try{
      await this.connect();
      const hs=await this.waitComposer(30000);
      if(hs.blockedBy)return {status:'blocked',text:`blocked:${hs.blockedBy}`,metadata:{agent_id:this.id,port:this.port,url:hs.href}};
      const fresh=options.fresh??this.fresh;
      const freshOpened=fresh?await this.freshChat():false;
      const before=await this.bodyText();
      const baseline=before.split(expectedText).length-1;
      const prompt=`${requestMarker}\nReply with exactly this token, with no other text:\n${expectedText}`;
      const submitMethod=await this.submitPrompt(prompt,requestMarker);
      const deadline=Date.now()+(options.timeoutMs||this.config.timeoutMs||180000);
      while(Date.now()<deadline){
        const s=await this.uiState();
        if(s.blockedBy)throw new Error(`BLOCKED:${s.blockedBy}`);
        const body=await this.bodyText();
        if(body.split(expectedText).length-1>baseline&&!s.stop){
          return {status:'ok',text:expectedText,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,url:s.href,fresh_chat:freshOpened,submit_method:submitMethod,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started,capture:'exact-token'}};
        }
        await new Promise(r=>setTimeout(r,500));
      }
      throw new Error('META_EXACT_TOKEN_TIMEOUT');
    }catch(e){
      const blocked=/^BLOCKED:/.test(e.message);
      return {status:blocked?'blocked':'error',text:e.message,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,transport:'browser-cdp',zero_cost_path:true,latency_ms:Date.now()-started}};
    }
  }
}
