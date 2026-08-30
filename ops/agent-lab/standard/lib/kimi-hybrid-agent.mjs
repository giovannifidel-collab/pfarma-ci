import { spawnSync } from 'node:child_process';
import crypto from 'node:crypto';
import { KeyboardBrowserAgent } from './keyboard-browser-agent.mjs';

function cliAvailable(){const r=spawnSync('bash',['-lc','command -v kimi >/dev/null 2>&1'],{stdio:'ignore'});return r.status===0;}
function parseEnvelope(stdout,begin,end){const s=String(stdout||'');const i=s.lastIndexOf(begin);if(i<0)return null;const j=s.indexOf(end,i+begin.length);if(j<0)return null;return s.slice(i+begin.length,j).trim();}
function standardToken(stdout){return String(stdout||'').match(/HIVE_STANDARD_OK:kimi:[A-F0-9]+/)?.[0]||null;}

export class KimiHybridAgent{
  constructor(config,opts={}){this.config=config;this.id=config.id;this.browser=new KeyboardBrowserAgent(config,opts);}
  async health(){
    if(cliAvailable()){
      const v=spawnSync('kimi',['--version'],{encoding:'utf8',timeout:15000});
      if(v.status===0)return {status:'ok',text:'Kimi CLI available',metadata:{agent_id:this.id,transport:'kimi-cli',version:String(v.stdout||v.stderr||'').trim(),zero_cost_path:true}};
    }
    const h=await this.browser.health();if(h.status==='ok')h.metadata={...h.metadata,transport:'browser-cdp-fallback'};return h;
  }
  async run(task,options={}){
    const started=Date.now();const nonce=crypto.randomBytes(6).toString('hex').toUpperCase();
    const begin=`HIVE_ADAPTER_BEGIN:${this.id}:${nonce}`,end=`HIVE_ADAPTER_END:${this.id}:${nonce}`;
    if(cliAvailable()){
      const prompt=`HIVE standard adapter request ${nonce}. Execute USER_TASK. Put the actual final answer between the exact markers. Do not output placeholder words, XML tags, angle brackets, or credentials.\nUSER_TASK:\n${String(task)}\n\n${begin}\nFINAL_ANSWER_TO_USER_TASK\n${end}\nReplace FINAL_ANSWER_TO_USER_TASK with the real answer.`;
      const r=spawnSync('kimi',['-p',prompt],{encoding:'utf8',timeout:options.timeoutMs||240000,maxBuffer:16*1024*1024,env:process.env});
      const stdout=String(r.stdout||'');let text=parseEnvelope(stdout,begin,end);
      if(r.status===0&&text===null)text=options.expectedText && stdout.includes(String(options.expectedText)) ? String(options.expectedText) : standardToken(stdout);
      if(r.status===0&&text!==null)return {status:'ok',text,metadata:{agent_id:this.id,provider:this.config.product,transport:'kimi-cli',zero_cost_path:true,latency_ms:Date.now()-started,nonce,capture:text.startsWith('HIVE_STANDARD_OK:')?'standard-token':'envelope'}};
      const cliError=String(r.stderr||stdout||r.error?.message||`CLI_EXIT_${r.status}`).trim().slice(-3000);
      const fallback=await this.browser.run(task,options);fallback.metadata={...fallback.metadata,kimi_cli_fallback_reason:cliError,transport:fallback.metadata?.transport||'browser-cdp'};return fallback;
    }
    return this.browser.run(task,options);
  }
  close(){this.browser.close();}
}
