# HIVE Agent Standard Layer

Phase B turns the ten independently certified providers into one runtime contract without integrating them into Queen/HIVE prematurely.

## Contract

```js
const agent = getAgent('claude')
const result = await agent.run(task)
// { status: 'ok'|'error'|'blocked', text, metadata }
```

`agent.health()` uses the same normalized envelope.

## Certified baseline

Kimi, Claude, Gemini, DeepSeek, Qwen, Mistral, Perplexity, Copilot, Meta AI and Duck.ai are the ten Phase-A certified providers. Grok Fast is intentionally excluded because it is not certified.

Kimi is a hybrid compatibility adapter: it prefers the already established Kimi Code CLI transport and falls back to the persistent browser/CDP route if a usable Kimi browser session exists. The other nine use the persistent certified browser profiles and their CDP ports.

## One-command runtime proof

```bash
bash ops/agent-lab/standard/standardize-all.sh
```

The command performs syntax/static gates, health checks, a real `agent.run()` roundtrip for every provider, exact output verification, and writes a JSON report under `ops/agent-lab/standard/reports/`.

Only a report with `STANDARDIZED=10/10` and `READY_FOR_HIVE_INTEGRATION=true` promotes the portfolio to Phase C. Code presence or static CI alone never changes `registry.json` from `standardized_count: 0`.

Useful scoped modes:

```bash
bash ops/agent-lab/standard/standardize-all.sh --health
bash ops/agent-lab/standard/standardize-all.sh --only claude,gemini
bash ops/agent-lab/standard/standardize-all.sh --retry-failed
```

Single adapter call:

```bash
node ops/agent-lab/standard/run-one.mjs meta "Return the number 42"
```

No commercial API key is required by this layer; it reuses free/authenticated browser sessions or the existing Kimi Code identity path.
