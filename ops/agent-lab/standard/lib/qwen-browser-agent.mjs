import { KeyboardBrowserAgent } from './keyboard-browser-agent.mjs';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const now = () => Date.now();

function qwenProviderBlock(text) {
  const s = String(text || '');
  if (/you have reached the daily usage limit/i.test(s)) return 'qwen_daily_usage_limit';
  if (/daily usage limit/i.test(s) && /wait\s+\d+\s+hours?/i.test(s)) return 'qwen_daily_usage_limit';
  if (/issue connecting to qwen/i.test(s) && /usage limit/i.test(s)) return 'qwen_daily_usage_limit';
  return null;
}

export class QwenBrowserAgent extends KeyboardBrowserAgent {
  async connect() {
    let lastError = null;
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        return await super.connect();
      } catch (e) {
        lastError = e;
        const retryable = /^(CDP_TIMEOUT_Runtime\.enable|CDP_CONNECT_TIMEOUT|CDP_CONNECT_ERROR|PAGE_WEBSOCKET_NOT_FOUND)$/.test(String(e.message || ''));
        if (!retryable || attempt === 3) throw e;
        this.close();
        await sleep(700 * attempt);
      }
    }
    throw lastError || new Error('QWEN_CDP_CONNECT_FAILED');
  }

  async run(task, options = {}) {
    const expectedText = options.expectedText ? String(options.expectedText) : null;
    if (!expectedText) return super.run(task, options);

    const started = now();
    let baselineExpectedCount = 0;
    let lastCount = 0;
    let lastBody = '';
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
      const preBlock = qwenProviderBlock(before);
      if (preBlock) {
        return {
          status:'blocked',
          text:`blocked:${preBlock}`,
          metadata:{agent_id:this.id,provider:this.config.product,port:this.port,url:hs.href,fresh_chat:freshOpened,transport:'browser-cdp',zero_cost_path:true,provider_block:preBlock,latency_ms:now()-started}
        };
      }
      baselineExpectedCount = before.split(expectedText).length - 1;

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
        const providerBlock = qwenProviderBlock(body);
        if (providerBlock) {
          return {
            status:'blocked',
            text:`blocked:${providerBlock}`,
            metadata:{agent_id:this.id,provider:this.config.product,port:this.port,url:s.href,fresh_chat:freshOpened,transport:'browser-cdp',zero_cost_path:true,provider_block:providerBlock,latency_ms:now()-started}
          };
        }
        const count = body.split(expectedText).length - 1;
        lastBody = body;
        lastCount = count;
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

      const diagnostic = await this.eval(`(()=>{
        const token=${JSON.stringify(expectedText)};
        const visible=e=>{try{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'}catch{return false}};
        const all=[...document.querySelectorAll('body *')];
        const matches=[];
        for(const e of all){
          const own=String(e.innerText||e.textContent||'');
          if(!own.includes(token))continue;
          const childHas=[...e.children].some(c=>String(c.innerText||c.textContent||'').includes(token));
          if(childHas)continue;
          matches.push({
            tag:e.tagName?.toLowerCase()||null,
            role:e.getAttribute?.('role')||null,
            aria:e.getAttribute?.('aria-label')||null,
            cls:String(e.className||'').slice(0,180),
            visible:visible(e),
            text:own.slice(0,500)
          });
          if(matches.length>=12)break;
        }
        const buttons=[...document.querySelectorAll('button,[role="button"]')].filter(visible).map(e=>String(e.getAttribute('aria-label')||e.innerText||'').trim()).filter(Boolean).slice(-30);
        return {href:String(location.href||''),title:document.title,matches,buttons};
      })()`).catch(()=>({href:null,title:null,matches:[],buttons:[]}));

      const state = await this.uiState().catch(()=>({stop:null,composer:null,composerText:''}));
      const diag = {
        baseline:baselineExpectedCount,
        count:lastCount,
        delta:lastCount-baselineExpectedCount,
        stop:state.stop,
        composer:state.composer,
        composer_text:String(state.composerText||'').slice(0,240),
        href:diagnostic.href,
        matches:diagnostic.matches,
        buttons:diagnostic.buttons,
        tail:lastBody.slice(-2200)
      };
      throw new Error(`QWEN_EXACT_RESPONSE_TIMEOUT_DIAG:${JSON.stringify(diag)}`);
    } catch (e) {
      const blocked = /^BLOCKED:/.test(e.message);
      return {
        status:blocked?'blocked':'error',
        text:e.message,
        metadata:{agent_id:this.id,provider:this.config.product,port:this.port,transport:'browser-cdp',zero_cost_path:true,latency_ms:now()-started,baseline_expected_count:baselineExpectedCount,last_expected_count:lastCount}
      };
    }
  }
}
