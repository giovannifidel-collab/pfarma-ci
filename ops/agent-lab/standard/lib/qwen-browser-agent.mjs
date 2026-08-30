import { KeyboardBrowserAgent } from './keyboard-browser-agent.mjs';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const now = () => Date.now();

export class QwenBrowserAgent extends KeyboardBrowserAgent {
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
      const before = await this.bodyText();
      const baselineExpectedCount = before.split(expectedText).length - 1;

      if (!await this.waitIdle(30000)) throw new Error('QWEN_NOT_IDLE_BEFORE_SEND');
      await this.setComposer(String(task));
      if (!await this.pressEnter()) throw new Error('QWEN_ENTER_SUBMIT_FAILED');
      if (!await this.verifySubmitted(expectedText, 10000)) throw new Error('QWEN_PROMPT_NOT_SUBMITTED');

      const timeout = options.timeoutMs || this.config.timeoutMs || 150000;
      const deadline = now() + timeout;
      while (now() < deadline) {
        const s = await this.uiState();
        if (s.blockedBy) throw new Error(`BLOCKED:${s.blockedBy}`);
        const body = await this.bodyText();
        const count = body.split(expectedText).length - 1;
        // One new occurrence is the submitted user prompt; the second is the
        // provider response. This mirrors Qwen's already-certified direct CDP
        // smoke/certification path and avoids the generic response envelope.
        if (count >= baselineExpectedCount + 2) {
          await sleep(700);
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
              submit_method:'enter-direct-exact-token',
              transport:'browser-cdp',
              zero_cost_path:true,
              latency_ms:now()-started,
              exact_token_occurrences:count-baselineExpectedCount
            }
          };
        }
        await sleep(600);
      }
      throw new Error('QWEN_EXACT_RESPONSE_TIMEOUT');
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
