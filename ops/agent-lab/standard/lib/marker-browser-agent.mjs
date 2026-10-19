import crypto from 'node:crypto';
import { KeyboardBrowserAgent } from './keyboard-browser-agent.mjs';

const now=()=>Date.now();

export class MarkerBrowserAgent extends KeyboardBrowserAgent {
  async run(task, options={}) {
    // Exact-output probes (used by HIVE runtime standardization) must use the
    // same strict envelope implementation as the shared BrowserAgent.  The
    // older Copilot-specific numbered protocol could be echoed verbatim by
    // Copilot, making the transport parser read protocol text as the answer.
    if (options.expectedText) return super.run(task, options);

    const started=now();
    const nonce=crypto.randomBytes(6).toString('hex').toUpperCase();
    const requestMarker=`HIVE_ADAPTER_REQUEST:${this.id}:${nonce}`;
    const begin=`HIVE_ADAPTER_BEGIN:${this.id}:${nonce}`;
    const end=`HIVE_ADAPTER_END:${this.id}:${nonce}`;
    try {
      await this.connect();
      const hs=await this.waitComposer(30000);
      if(hs.blockedBy) return {status:'blocked',text:`blocked:${hs.blockedBy}`,metadata:{agent_id:this.id,port:this.port,url:hs.href}};
      const fresh=options.fresh ?? this.fresh;
      const freshOpened=fresh ? await this.freshChat() : false;
      const before=await this.bodyText();
      const prompt=[
        requestMarker,
        'USER_TASK:',
        String(task),
        '',
        'OUTPUT_PROTOCOL:',
        'Complete USER_TASK first. Then output exactly three parts in this order:',
        `1. ${begin}`,
        '2. The actual final answer to USER_TASK, with no labels or placeholder words.',
        `3. ${end}`,
        'Do not repeat the request marker.'
      ].join('\n');
      const submitMethod=await this.submitPrompt(prompt,requestMarker);
      const text=await this.waitEnvelope(begin,end,options.timeoutMs||this.config.timeoutMs||180000,null,0);
      const s=await this.uiState();
      return {status:'ok',text,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,url:s.href,fresh_chat:freshOpened,submit_method:submitMethod,transport:'browser-cdp',zero_cost_path:true,latency_ms:now()-started,nonce}};
    } catch(e) {
      const blocked=/^BLOCKED:/.test(e.message);
      return {status:blocked?'blocked':'error',text:e.message,metadata:{agent_id:this.id,provider:this.config.product,port:this.port,transport:'browser-cdp',zero_cost_path:true,latency_ms:now()-started,nonce}};
    }
  }
}
