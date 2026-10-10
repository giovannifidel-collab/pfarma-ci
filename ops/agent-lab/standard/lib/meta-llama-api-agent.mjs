const DEFAULT_BASE_URL = 'https://api.llama.com/v1';
const DEFAULT_MODEL = 'Llama-4-Maverick-17B-128E-Instruct-FP8';

const cleanBase = value => String(value || DEFAULT_BASE_URL).replace(/\/+$/, '');
const sleep = ms => new Promise(r => setTimeout(r, ms));

export class MetaLlamaApiAgent {
  constructor(config) {
    this.config = config;
    this.id = config.id;
    this.baseUrl = cleanBase(process.env.LLAMA_API_BASE_URL);
    this.apiKey = String(process.env.LLAMA_API_KEY || '').trim();
    this.model = String(process.env.HIVE_META_LLAMA_MODEL || '').trim() || null;
  }

  headers() {
    return {
      'Authorization': `Bearer ${this.apiKey}`,
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    };
  }

  async request(path, options = {}, timeoutMs = 30000) {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers: { ...this.headers(), ...(options.headers || {}) },
      signal: AbortSignal.timeout(timeoutMs)
    });
    let body = null;
    try { body = await response.json(); } catch { body = null; }
    return { response, body };
  }

  async resolveModel(force = false) {
    if (this.model && !force) return this.model;
    const { response, body } = await this.request('/models', { method:'GET' }, 20000);
    if (response.status === 401 || response.status === 403) throw new Error('LLAMA_API_AUTH_REQUIRED');
    if (response.status === 429) throw new Error('LLAMA_API_RATE_LIMIT');
    if (!response.ok) throw new Error(`LLAMA_API_MODELS_HTTP_${response.status}`);

    const models = Array.isArray(body) ? body : (Array.isArray(body?.data) ? body.data : []);
    const ids = models.map(x => String(x?.id || '')).filter(Boolean);
    if (!ids.length) throw new Error('LLAMA_API_NO_MODELS');

    const configured = String(process.env.HIVE_META_LLAMA_MODEL || '').trim();
    if (configured) {
      if (!ids.includes(configured)) throw new Error(`LLAMA_MODEL_NOT_AVAILABLE:${configured}`);
      this.model = configured;
      return this.model;
    }

    this.model = ids.find(x => x === DEFAULT_MODEL)
      || ids.find(x => /maverick.*instruct/i.test(x))
      || ids.find(x => /scout.*instruct/i.test(x))
      || ids.find(x => /instruct/i.test(x))
      || ids[0];
    return this.model;
  }

  async health() {
    const started = Date.now();
    if (!this.apiKey) {
      return {
        status:'blocked',
        text:'LLAMA API key required',
        metadata:{agent_id:this.id,transport:'meta-llama-api',base_url:this.baseUrl,latency_ms:Date.now()-started}
      };
    }
    try {
      const model = await this.resolveModel(true);
      return {
        status:'ok',
        text:'Meta Llama API ready',
        metadata:{agent_id:this.id,transport:'meta-llama-api',provider:'Meta Llama API',model,base_url:this.baseUrl,latency_ms:Date.now()-started}
      };
    } catch (e) {
      const msg = String(e?.message || e || 'LLAMA_API_HEALTH_ERROR');
      const blocked = /AUTH_REQUIRED|RATE_LIMIT|key required/i.test(msg);
      return {
        status:blocked?'blocked':'error',
        text:msg,
        metadata:{agent_id:this.id,transport:'meta-llama-api',base_url:this.baseUrl,latency_ms:Date.now()-started}
      };
    }
  }

  extractText(body) {
    const content = body?.completion_message?.content;
    if (typeof content === 'string') return content.trim();
    if (content && typeof content === 'object' && typeof content.text === 'string') return content.text.trim();
    return '';
  }

  async run(task, options = {}) {
    const started = Date.now();
    if (!this.apiKey) {
      return {status:'blocked',text:'LLAMA API key required',metadata:{agent_id:this.id,transport:'meta-llama-api'}};
    }
    try {
      const model = await this.resolveModel();
      const expected = options.expectedText ? String(options.expectedText) : null;
      const userContent = expected
        ? `Return exactly this token and nothing else: ${expected}`
        : String(task || '');
      const payload = {
        model,
        messages:[
          {role:'system',content:'Follow the user instruction exactly. If an exact token is requested, output only that token with no markdown, punctuation, prefix, suffix, or explanation.'},
          {role:'user',content:userContent}
        ],
        temperature:0,
        max_completion_tokens:96,
        stream:false,
        response_format:{type:'text'}
      };
      const { response, body } = await this.request('/chat/completions', {
        method:'POST',
        body:JSON.stringify(payload)
      }, this.config.timeoutMs || 120000);

      if (response.status === 401 || response.status === 403) {
        return {status:'blocked',text:'LLAMA API authentication required',metadata:{agent_id:this.id,transport:'meta-llama-api',model,http_status:response.status}};
      }
      if (response.status === 429) {
        return {status:'blocked',text:'LLAMA API rate limit',metadata:{agent_id:this.id,transport:'meta-llama-api',model,http_status:response.status}};
      }
      if (!response.ok) {
        return {status:'error',text:`LLAMA_API_HTTP_${response.status}`,metadata:{agent_id:this.id,transport:'meta-llama-api',model,http_status:response.status,api_error:body?.error?.message || body?.message || null}};
      }

      const text = this.extractText(body);
      if (!text) {
        return {status:'error',text:'LLAMA_API_EMPTY_RESPONSE',metadata:{agent_id:this.id,transport:'meta-llama-api',model,request_id:body?.id || null}};
      }
      return {
        status:'ok',
        text,
        metadata:{agent_id:this.id,provider:'Meta Llama API',transport:'meta-llama-api',model,request_id:body?.id || null,zero_cost_path:true,latency_ms:Date.now()-started}
      };
    } catch (e) {
      return {
        status:'error',
        text:String(e?.message || e || 'LLAMA_API_RUN_ERROR'),
        metadata:{agent_id:this.id,provider:'Meta Llama API',transport:'meta-llama-api',latency_ms:Date.now()-started}
      };
    }
  }

  async recover(reason = 'unknown') {
    this.model = null;
    await sleep(300);
    const h = await this.health();
    return {recovered:h.status === 'ok',method:'meta-llama-api-recheck',reason,status:h.status,model:h.metadata?.model || null};
  }

  close() {}
}
