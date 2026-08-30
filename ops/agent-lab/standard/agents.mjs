import { BrowserAgent } from './lib/browser-agent.mjs';

export const AGENT_CONFIGS = [
  {
    id:'kimi', product:'Kimi Web', port:9223, scanPorts:[9223], startScript:'kimi/start-browser.sh',
    targetPattern:/kimi\.(com|ai)|moonshot/i,
    composerPatterns:['ask.*kimi','message.*kimi','chat with kimi','send a message','^message$'],
    submitPatterns:['^send$','send message','submit'],
    blockPatterns:['log in to kimi','sign in to kimi','continue with.*(google|apple|phone)'], freshChat:true
  },
  {
    id:'claude', product:'Claude Web', port:9224, startScript:'claude/start-browser.sh', targetPattern:/claude\.ai/i,
    composerPatterns:['message claude','ask claude','send a message','^message$'], submitPatterns:['send message','^send$'],
    blockPatterns:['log in to claude','sign in to claude'], freshChat:true
  },
  {
    id:'gemini', product:'Gemini Web', port:9225, startScript:'gemini/start-browser.sh', targetPattern:/gemini\.google\.com/i,
    composerPatterns:['enter a prompt','ask gemini','message gemini','prompt'], submitPatterns:['send message','^send$'],
    blockPatterns:['sign in to gemini','log in to gemini'], freshChat:true
  },
  {
    id:'deepseek', product:'DeepSeek Web', port:9227, startScript:'deepseek/start-browser.sh', targetPattern:/chat\.deepseek\.com|deepseek\.com/i,
    composerPatterns:['message deepseek','ask deepseek','send a message','^message$'], submitPatterns:['^send$','send message'],
    blockPatterns:['log in to deepseek','sign in to deepseek'], freshChat:true
  },
  {
    id:'qwen', product:'Qwen Web', port:9228, startScript:'qwen/start-browser.sh', targetPattern:/chat\.qwen\.ai/i,
    composerPatterns:['ask qwen','message qwen','send a message'], submitPatterns:['^send$','send message','submit'],
    blockPatterns:['log in to qwen','sign in to qwen'], freshChat:true
  },
  {
    id:'mistral', product:'Mistral Vibe Web / Fast', port:9229, startScript:'mistral/start-browser.sh', targetPattern:/chat\.mistral\.ai/i,
    composerPatterns:['ask.*mistral','message.*mistral','send a message','^message$'], submitPatterns:['^send$','send message'],
    blockPatterns:['log in to mistral','sign in to mistral'], freshChat:true
  },
  {
    id:'perplexity', product:'Perplexity Web', port:9230, startScript:'perplexity/start-browser.sh', targetPattern:/perplexity\.ai/i,
    composerPatterns:['ask anything','ask perplexity','message perplexity','^ask$'], submitPatterns:['submit','^ask$','^send$','send message'],
    blockPatterns:['sign in to perplexity','log in to perplexity'], freshChat:true, timeoutMs:210000
  },
  {
    id:'copilot', product:'Microsoft Copilot Web / Standard chat', port:9231, startScript:'copilot/start-browser.sh', targetPattern:/copilot\.(com|microsoft\.com)/i,
    composerPatterns:['message copilot','ask copilot','send a message'], submitPatterns:['^send$','send message','submit'],
    blockPatterns:['sign in to copilot','log in to copilot'], freshChat:true, timeoutMs:210000
  },
  {
    id:'meta', product:'Meta AI Web / Instant', port:9232, startScript:'meta/start-browser.sh', targetPattern:/meta\.ai/i,
    composerPatterns:['ask meta ai','message meta ai','^message$'], submitPatterns:['^send$','send message','submit'],
    blockPatterns:['log in to meta ai','sign in to meta ai'], freshChat:true
  },
  {
    id:'duck', product:'Duck.ai Web / Free / Fast', port:9233, startScript:'duck/start-browser.sh', targetPattern:/duck\.ai/i,
    composerPatterns:['ask anything privately'], submitPatterns:['^send$','^ask$'],
    blockPatterns:['daily limit','rate limit','usage limit','limit reached','you.ve reached.*limit'], freshChat:true
  }
];

export function buildAgents({ rootDir, fresh = true } = {}) {
  return new Map(AGENT_CONFIGS.map(c => [c.id, new BrowserAgent(c, { rootDir, fresh })]));
}
