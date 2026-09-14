# HIVE Agent Gateway v1

Permanent browser-agent host for SUPER AI HIVE. This package moves the browser data plane away from GitHub Codespaces without changing Queen, the common agent contract, or the strict 10/10 gate.

## Scope

Current logical state remains unchanged while the gateway is being deployed:

- Queen/core/runtime: already operational.
- Managed agents: 8/10.
- Deferred: `kimi`, `meta`.
- Strict 10/10 gate: preserved.
- Existing contract: `agent.run(task) -> {status,text,metadata}`.

This package does **not** certify agents and does **not** modify Queen registry/proof/runtime locks.

## Target layout

```text
Cloudflare / Queen
       |
Cloudflare Access + Named Tunnel
       |
HIVE Agent Gateway (Wyse 5070 / always-on Linux)
       |
127.0.0.1:9240  async-job-v1 bridge
       |
CDP browser fabric on localhost
```

The bridge remains `ops/agent-lab/bridge/server.mjs`. Browser agents continue to launch on demand using their existing scripts and persistent profiles.

## Persistent paths

```text
/opt/hive/pfarma-ci                         repository checkout
/var/lib/hive-agent-gateway                 service home/state
/var/lib/hive-agent-gateway/.hive-agent-lab browser profiles
/etc/hive-agent-gateway/gateway.env         bridge configuration + stable token
/etc/hive-agent-gateway/cloudflare.env      Named Tunnel token
```

Secrets are never committed to Git.

## Install on the permanent Linux node

Clone the branch and run the installer as root. If the stable bridge token has been exported from the previous host to a local protected file, pass it with `--token-file`.

```bash
git clone --branch hive-cloud-computer-v0 https://github.com/giovannifidel-collab/pfarma-ci.git
cd pfarma-ci
sudo bash ops/agent-gateway/install.sh --token-file /path/to/protected/bridge-token
```

If the token is not supplied, installation completes but the bridge is deliberately **not started**. The installer never silently generates a replacement token.

Optional Named Tunnel token:

```bash
sudo bash ops/agent-gateway/install.sh \
  --token-file /path/to/protected/bridge-token \
  --cloudflare-token-file /path/to/protected/cloudflare-tunnel-token
```

The Cloudflare hostname itself must be configured to target `http://127.0.0.1:9240` and protected by Cloudflare Access / Service Auth.

## Browser sessions

The service user is `hive`; its `HOME` is `/var/lib/hive-agent-gateway`. Existing Agent Lab scripts therefore persist browser profiles under:

```text
/var/lib/hive-agent-gateway/.hive-agent-lab/
```

To import an existing Agent Lab state directory safely:

```bash
sudo bash ops/agent-gateway/migrate-browser-state.sh /path/to/exported/.hive-agent-lab
```

The migration excludes runtime PIDs/logs and does not overwrite the stable bridge token.

If a provider session cannot be migrated, authenticate it once through the existing noVNC desktop. After that, the profile persists across service restarts and reboots.

## Services

```text
hive-agent-gateway.service              bridge, Restart=always
hive-agent-gateway-health.timer         local authenticated watchdog
hive-agent-gateway-cloudflared.service  stable Named Tunnel (only enabled when configured)
```

Useful checks:

```bash
sudo systemctl status hive-agent-gateway --no-pager
sudo systemctl status hive-agent-gateway-health.timer --no-pager
sudo bash /opt/hive/pfarma-ci/ops/agent-gateway/healthcheck.sh
```

A local healthy bridge should report:

```text
LOCAL_HEALTH=PASS
LOCAL_AUTH=PASS
BRIDGE_PROTOCOL=async-job-v1
```

Public health is checked only when a public URL and Cloudflare Service Token credentials are installed locally.

## Network/security rules

- Keep CDP ports and port `9240` on localhost only.
- Do not expose Chromium debugging ports to LAN/Internet.
- Use a Cloudflare **Named Tunnel**, not a Quick Tunnel, for the permanent path.
- Keep Cloudflare Access in front of the tunnel.
- Keep bridge bearer-token authentication enabled behind Cloudflare Access.
- Use Tailscale for administration; noVNC should be reachable only through a trusted administrative path.
- Never print or commit bridge, Cloudflare, bearer, or client-secret values.

## Completion gate

Do not claim migration complete merely because these files exist. Completion requires proof on the real always-on node:

```text
HIVE_AGENT_GATEWAY=READY
CODESPACE_DEPENDENCY=false
BRIDGE_AUTOSTART=PASS
TUNNEL_STABLE=PASS
LIVE_BROWSER_DATA_PLANE=PASS
```

Then perform fresh live calls against the currently managed 8 agents. This validates the new host; it does not repeat the completed standardization campaign and does not promote Kimi or Meta.