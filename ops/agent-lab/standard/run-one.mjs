import { getAgent, agentIds } from './index.mjs';

const [id, ...parts] = process.argv.slice(2);
if (!id || !agentIds.includes(id)) {
  console.error(`Usage: node run-one.mjs <${agentIds.join('|')}> <task>`);
  process.exit(64);
}
const task = parts.join(' ').trim();
if (!task) { console.error('ERROR: task is required'); process.exit(64); }
const agent = getAgent(id);
const result = await agent.run(task, { fresh:true });
console.log(JSON.stringify(result, null, 2));
agent.close();
process.exit(result.status === 'ok' ? 0 : 2);
