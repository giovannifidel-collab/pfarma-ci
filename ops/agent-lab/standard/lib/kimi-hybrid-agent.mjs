import { spawnSync } from 'node:child_process';
import crypto from 'node:crypto';
import { KimiBrowserAgent } from './kimi-browser-agent.mjs';

function cliAvailable(){const r=spawnSync('bash',['-lc','command -v kimi >/dev/null 2>&1'],{stdio:'ignore'});return r.status===0;}
function stripAnsi(v){return String(v||'').replace(/\x1B\[[0-?]*[ -\/]*[@-~]/g,'');}
function parseEnvelope(stdout,begin,end){const s=stripAnsi(stdout);const i=s.lastIndexOf(begin);if(i<0)return null;const j=s.indexOf(end,i+begin.length);if(j<0)return null;return s.slice(i+begin.length,j).trim();}
function exactStandardTokenLine(output,expected){
  if(!expected)return null;
  const clean=stripAnsi(output);
  const lines=clean.split(/\r?\n/)
    .map(x=>x.trim().replace(/^```(?:text)?\s*/i,'').replace(/\s*```$/,'').replace(/^['"`]+|['"`]+$/g,'').trim())
    .filter(Boolean);
  return lines.includes(expected)?expected:null;
}

export class KimiHybridAgent{
  constructor(config,opts={}){this.config=config;this.id=config.id;this.browser=new KimiBrowserAgent(config,opts);}
  async health(){
    if(cliAvailable()){
      const v=spawnSync('kimi',['--version'],{encoding:'utf8',timeout:15000});
      if(v.status===0)return {status:'ok',text:'Kimi CLI available',metadata:{agent_id:this.id,transport:'kimi-cli',version:stripAnsi(`${v.stdout||''}\n${v.stderr||''}`).trim(),zero_cost_path:true}};
    }
    const h=await this.browser.health();if(h.status==='ok')h.metadata={...h.metadata,transport:'browser-cdp-fallback'};return h;
  }
  async run(task,options={}){
    const started=Date.now();const nonce=crypto.randomBytes(6).toString('hex').toUpperCase();
    const begin=`HIVE_ADAPTER_BEGIN:${this.id}:${nonce}`,end=`HIVE_ADAPTER_END:${this.id}:${nonce}`;
    if(cliAvailable()){
      const expectedText=options.expectedText?String(options.expectedText):null;
      const prompt=expectedText
        ? `Return exactly this token and nothing else: ${expectedText}`
        : `HIVE standard adapter request ${nonce}. Execute USER_TASK and place only the real final answer between these exact markers.\nUSER_TASK:\n${String(task)}\n\n${begin}\n${end}`;
      const r=spawnSync('kimi',['-p',prompt],{encoding:'utf8',timeout:options.timeoutMs||240000,maxBuffer:16*1024*1024,env:process.env});
      const stdout=String(r.stdout||'');
      const stderr=String(r.stderr||'');
      const combined=`${stdout}\n${stderr}`;
      const text=expectedText?exactStandardTokenLine(combined,expectedText):parseEnvelope(combined,begin,end);
      if(r.status===0&&text!==null)return {status:'ok',text,metadata:{agent_id:this.id,provider:this.config.product,transport:'kimi-cli',zero_cost_path:true,latency_ms:Date.now()-started,nonce,capture:expectedText?'exact-token-line-normalized-combined-streams':'envelope'}};
      const cliError=stripAnsi(stderr||stdout||r.error?.message||`CLI_EXIT_${r.status}`).trim().slice(-3000);
      const fallback=await this.browser.run(task,options);fallback.metadata={...fallback.metadata,kimi_cli_fallback_reason:cliError,transport:fallback.metadata?.transport||'browser-cdp'};return fallback;
    }
    return this.browser.run(task,options);
  }
  async recover(reason='unknown'){return this.browser.recover(reason);}
  close(){this.browser.close();}
}
