import relay from './index.js';
import { serveKimiSessionToDispatcher } from './github-oidc.js';

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === '/dispatcher/session') {
      return serveKimiSessionToDispatcher(request, env);
    }
    return relay.fetch(request, env, ctx);
  },
};
