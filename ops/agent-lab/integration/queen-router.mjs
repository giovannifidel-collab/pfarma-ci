import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { agentIds, getAgent, closeAll } from '../standard/index.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REGISTRY_PATH = path.resolve(HERE, '../standard/registry.json');
const sleep = ms => new Promise(r => setTimeout(r, ms));

function readRegistry() {
  return JSON.parse(fs.readFileSync(REGISTRY_PATH, 'utf8'));
}

function assertFabricReady({ allowIntegrationPhase = true } = {}) {
  const registry = readRegistry();
  const allowed = allowIntegrationPhase ? ['C_STANDARDIZED','D_HIVE_INTEGRATION','E_HIVE_INTEGRATED'] : ['E_HIVE_INTEGRATED'];
  if (!allowed.includes(registry.phase)) throw new Error(`QUEEN_FABRIC_REGISTRY_PHASE:${registry.phase}`);
  if (registry.standardized_count !== 10 || registry.agents?.filter(a => a.standardized === true).length !== 10) {
    throw new Error('QUEEN_FABRIC_STANDARDIZATION_REQUIRED');
  }
  return registry;
}

export class QueenAgentFabric {
  constructor({ attempts = 2, retryDelayMs = 1200, requireIntegrated = false } = {}) {
    this.attempts = Math.max(1, Math.min(Number(attempts) || 2, 4));
    this.retryDelayMs = Math.max(0, Math.min(Number(retryDelayMs) || 1200, 30000));
    this.registry = assertFabricReady({ allowIntegrationPhase: !requireIntegrated });
    this.requireIntegrated = requireIntegrated;
    if (requireIntegrated && (this.registry.hive_integrated_count !== 10 || this.registry.agents?.filter(a => a.hive_integrated === true).length !== 10)) {
      throw new Error('QUEEN_FABRIC_INTEGRATION_REQUIRED');
    }
  }

  async invoke(id, task, options = {}) {
    const normalizedId = String(id || '').toLowerCase();
    if (!agentIds.includes(normalizedId)) {
      return { status:'error', text:`UNKNOWN_AGENT:${normalizedId}`, metadata:{ agent_id:normalizedId, queen_route:'direct', attempts:0 } };
    }
    const agent = getAgent(normalizedId);
    const attempts = Math.max(1, Math.min(Number(options.attempts || this.attempts), 4));
    const trace = [];
    let last = null;

    for (let attempt = 1; attempt <= attempts; attempt++) {
      const started = Date.now();
      try {
        const health = await agent.health();
        if (health.status !== 'ok') {
          last = { status:health.status, text:health.text, metadata:{...(health.metadata||{}),agent_id:normalizedId} };
          trace.push({attempt,stage:'health',status:health.status,text:health.text,latency_ms:Date.now()-started});
        } else {
          const out = await agent.run(String(task), { fresh: options.fresh ?? true, timeoutMs: options.timeoutMs });
          last = out;
          trace.push({attempt,stage:'run',status:out.status,text:String(out.text||'').slice(0,500),latency_ms:Date.now()-started});
          if (out.status === 'ok') {
            return { ...out, metadata:{...(out.metadata||{}),queen_route:'direct',queen_attempt:attempt,queen_trace:trace} };
          }
          if (out.status === 'blocked') break;
        }
      } catch (e) {
        last = { status:'error', text:e.message, metadata:{agent_id:normalizedId} };
        trace.push({attempt,stage:'exception',status:'error',text:e.message,latency_ms:Date.now()-started});
      }

      if (attempt < attempts) {
        try {
          if (typeof agent.recover === 'function') {
            const recovery = await agent.recover(`queen:${last?.text||'unknown'}`);
            trace.push({attempt,stage:'recovery',...recovery});
          } else {
            agent.close();
            trace.push({attempt,stage:'recovery',recovered:false,method:'close-only'});
          }
        } catch (e) {
          trace.push({attempt,stage:'recovery',recovered:false,error:e.message});
        }
        await sleep(this.retryDelayMs * attempt);
      }
    }

    return {
      status:last?.status || 'error',
      text:last?.text || 'QUEEN_AGENT_INVOCATION_FAILED',
      metadata:{...(last?.metadata||{}),agent_id:normalizedId,queen_route:'direct',queen_attempts:trace.length,queen_trace:trace}
    };
  }

  async fallback(ids, task, options = {}) {
    const chain = Array.isArray(ids) ? ids : [ids];
    const trace = [];
    for (const id of chain) {
      const out = await this.invoke(id, task, options);
      trace.push({id,status:out.status,text:String(out.text||'').slice(0,500)});
      if (out.status === 'ok') {
        return { ...out, metadata:{...(out.metadata||{}),queen_route:'fallback',queen_fallback_trace:trace} };
      }
    }
    return { status:'error', text:'QUEEN_FALLBACK_EXHAUSTED', metadata:{queen_route:'fallback',queen_fallback_trace:trace} };
  }

  async parallel(ids, task, options = {}) {
    const unique = [...new Set((Array.isArray(ids) ? ids : [ids]).map(x => String(x).toLowerCase()))];
    const entries = await Promise.all(unique.map(async id => [id, await this.invoke(id, task, options)]));
    const results = Object.fromEntries(entries);
    const passed = entries.filter(([,out]) => out.status === 'ok').length;
    return {
      status: passed === entries.length ? 'ok' : (passed ? 'partial' : 'error'),
      results,
      metadata:{queen_route:'parallel',requested:unique.length,passed,failed:entries.length-passed}
    };
  }

  close() { closeAll(); }
}

export function queenFabricStatus() {
  const registry = readRegistry();
  return {
    phase:registry.phase,
    standardized_count:registry.standardized_count,
    hive_integrated_count:registry.hive_integrated_count,
    agent_ids:[...agentIds]
  };
}
