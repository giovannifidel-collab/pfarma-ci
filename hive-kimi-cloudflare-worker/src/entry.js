import relay from './index.js';
import { serveKimiSessionToDispatcher } from './github-oidc.js';
import { handleAutoTask } from './auto-task.js';

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === '/dispatcher/session') {
      return serveKimiSessionToDispatcher(request, env);
    }

    if (url.pathname.startsWith('/auto/')) {
      const response = await handleAutoTask(request, env);
      if (response) return response;
    }

    if (url.pathname.startsWith('/auto-submit/')) {
      const response = await handleAutoTask(request, env);
      if (response) return response;
    }

    if (url.pathname.startsWith('/auto-result/')) {
      const response = await handleAutoTask(request, env);
      if (response) return response;
    }

    return relay.fetch(request, env, ctx);
  },
};
