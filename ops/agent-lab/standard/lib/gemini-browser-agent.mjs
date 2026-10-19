import { KeyboardBrowserAgent } from './keyboard-browser-agent.mjs';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const now = () => Date.now();
const count = (text, token) => token ? String(text || '').split(token).length - 1 : 0;

export class GeminiBrowserAgent extends KeyboardBrowserAgent {
  async assistantText() {
    return this.eval(`(()=>{
      const selectors=[
        'message-content','model-response','.model-response-text',
        '[data-test-id*="model-response" i]',
        '[data-message-author-role="model"]','[data-message-author-role="assistant"]'
      ];
      const chunks=[];
      for(const sel of selectors){
        for(const e of document.querySelectorAll(sel)){
          const t=String(e.innerText||e.textContent||'').trim();
          if(t)chunks.push(t);
        }
      }
      return [...new Set(chunks)].join('\\n');
    })()`).catch(() => '');
  }

  async run(task, options = {}) {
    const expectedText = options.expectedText ? String(options.expectedText) : null;
    if (!expectedText) return super.run(task, options);

    const started = now();
    try {
      await this.connect();
      const hs = await this.waitComposer(30000);
      if (hs.blockedBy) {
        return {
          status:'blocked',
          text:`blocked:${hs.blockedBy}`,
          metadata:{agent_id:this.id,provider:this.config.product,port:this.port,url:hs.href,transport:'browser-cdp',zero_cost_path:true,latency_ms:now()-started}
        };
      }

      const fresh = options.fresh ?? this.fresh;
      const freshOpened = fresh ? await this.freshChat() : false;
      const beforeAssistant = count(await this.assistantText(), expectedText);
      const beforeBody = count(await this.bodyText(), expectedText);

      const submitMethod = await this.submitPrompt(String(task), expectedText);
      const timeout = options.timeoutMs || this.config.timeoutMs || 150000;
      const deadline = now() + timeout;
      let proof = null;

      while (now() < deadline) {
        const s = await this.uiState();
        if (s.blockedBy) throw new Error(`BLOCKED:${s.blockedBy}`);

        const assistant = await this.assistantText();
        if (count(assistant, expectedText) > beforeAssistant) {
          proof = 'assistant-container-exact-token';
        } else {
          const body = await this.bodyText();
          if (count(body, expectedText) >= beforeBody + 2) proof = 'body-occurrence-exact-token';
        }

        if (proof && !s.stop) {
          await sleep(700);
          if (await this.waitIdle(20000)) {
            const finalState = await this.uiState();
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
                response_proof:proof,
                transport:'browser-cdp',
                zero_cost_path:true,
                latency_ms:now()-started
              }
            };
          }
        }
        await sleep(650);
      }

      throw new Error('GEMINI_EXACT_RESPONSE_TIMEOUT');
    } catch (e) {
      const blocked = /^BLOCKED:/.test(e.message);
      return {
        status:blocked?'blocked':'error',
        text:e.message,
        metadata:{agent_id:this.id,provider:this.config.product,port:this.port,transport:'browser-cdp',zero_cost_path:true,latency_ms:now()-started}
      };
    }
  }
}
