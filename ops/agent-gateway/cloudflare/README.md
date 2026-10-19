# Cloudflare Named Tunnel for HIVE Agent Gateway v1

The permanent Gateway must use a stable Cloudflare Named Tunnel. Do not use the previous `trycloudflare.com` Quick Tunnel for the always-on path.

## Required route

Configure one hostname in the Cloudflare tunnel with origin:

```text
http://127.0.0.1:9240
```

Keep Cloudflare Access in front of that hostname. The intended policy shape is:

- human/admin access as required;
- service-to-service access using Cloudflare Service Auth;
- bridge bearer-token authentication remains active behind Access.

The Cloudflare tunnel token is a separate secret from:

- `CF_ACCESS_CLIENT_ID`
- `CF_ACCESS_CLIENT_SECRET`
- `HIVE_AGENT_BRIDGE_TOKEN`

Do not overwrite or merge those credentials.

## Gateway configuration

Store only the Named Tunnel token locally:

```text
/etc/hive-agent-gateway/cloudflare.env
```

with mode `0600` and content equivalent to:

```text
HIVE_CLOUDFLARE_TUNNEL_TOKEN=<secret>
```

Never commit the value.

After the hostname and Access policy exist, place the public hostname (scheme included, no trailing path) in:

```text
/etc/hive-agent-gateway/gateway.env
```

as:

```text
HIVE_AGENT_GATEWAY_PUBLIC_URL=https://gateway.example.invalid
```

For end-to-end public verification, the same local file may contain the existing Cloudflare Service Token credentials used by the caller:

```text
CF_ACCESS_CLIENT_ID=<secret>
CF_ACCESS_CLIENT_SECRET=<secret>
```

The healthcheck sends them only as request headers and never prints their values.

## Verification

```bash
sudo systemctl restart hive-agent-gateway-cloudflared.service
sudo systemctl status hive-agent-gateway-cloudflared.service --no-pager
sudo /opt/hive/pfarma-ci/ops/agent-gateway/healthcheck.sh
```

Do not mark `TUNNEL_STABLE=PASS` until the public authenticated check succeeds against the real hostname.
