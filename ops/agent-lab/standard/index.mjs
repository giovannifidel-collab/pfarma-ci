import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildAgents, AGENT_CONFIGS } from './agents.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const AGENT_LAB_ROOT = path.resolve(HERE, '..');
const pool = buildAgents({ rootDir: AGENT_LAB_ROOT, fresh: true });

export const agentIds = Object.freeze(AGENT_CONFIGS.map(x => x.id));

export function getAgent(id) {
  const agent = pool.get(String(id).toLowerCase());
  if (!agent) throw new Error(`UNKNOWN_AGENT:${id}`);
  return agent;
}

export async function runAgent(id, task, options = {}) {
  return getAgent(id).run(task, options);
}

export async function healthAgent(id) {
  return getAgent(id).health();
}

export function closeAgent(id) {
  getAgent(id).close();
}

export function closeAll() {
  for (const agent of pool.values()) agent.close();
}
