# HIVE Agent Lab — Phase B Common Contract

Status: **interface scaffold only**. Creating this contract does not make any provider HIVE-integrated.

## Goal

All certified browser agents must expose one common execution surface before Queen/HIVE integration:

```js
const result = await agent.run(task)
```

with the normalized result:

```js
{
  status,   // "ok" | "error" | "blocked"
  text,     // final assistant text, empty only on non-ok results
  metadata  // transport/provider/session facts; never canonical HIVE memory
}
```

## Input

Minimum accepted task:

```js
{
  text: "..."
}
```

Normalized task:

```js
{
  text: "...",
  session: {
    id: null,
    fresh_chat: true
  },
  timeout_ms: 180000,
  metadata: {}
}
```

Rules:

1. `text` is required and non-empty.
2. `fresh_chat` defaults to `true` for providers whose certification requires a clean conversation.
3. Provider-specific prompt formatting stays inside the adapter.
4. Provider cookies/browser profiles stay local to the provider adapter.
5. No adapter may write canonical HIVE memory directly.

## Output

```js
{
  status: "ok",
  text: "provider response",
  metadata: {
    agent_id: "duck",
    provider: "Duck.ai",
    product: "Duck.ai Web",
    transport: "browser-session-direct-cdp",
    mode: "Fast",
    tier: "Free",
    authenticated: false,
    fresh_chat: true,
    started_at: "ISO-8601",
    finished_at: "ISO-8601",
    latency_ms: 1234,
    conversation_ref: null,
    certification_test_id: "HIVE-DUCK-STRESS-0003-FRESH"
  }
}
```

Errors must remain normalized:

```js
{
  status: "error",
  text: "",
  metadata: {
    agent_id: "...",
    error_code: "...",
    retryable: true
  }
}
```

Quota/auth walls use `status: "blocked"`, not `ok`.

## Mandatory adapter properties

Every adapter must implement:

```js
agent.id
agent.run(task)
agent.health()
```

`health()` must report observed runtime state and must not infer certification from code presence.

Minimum health shape:

```js
{
  browser_ready: true,
  session_ready: true,
  prompt_ok: true,
  capture_ok: true,
  certified: true,
  ready_for_hive: true
}
```

## Phase boundary

An adapter becomes `STANDARDIZED` only after a repeatable runtime test proves:

`common task -> agent.run() -> provider UI -> provider response -> normalized result`

Only `STANDARDIZED` agents may enter Phase C Queen/HIVE integration.
