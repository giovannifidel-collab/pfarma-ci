#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
TARGET="ops/agent-lab/bridge/public-runner-target.json"
URL_FILE="$HOME/.hive-agent-lab/agent-bridge/url"
WORKFLOW="hive-queen-public-runner.yml"
REPO="giovannifidel-collab/pfarma-ci"

[[ -f "$TARGET" ]] || { echo 'PUBLIC_RUNNER_TARGET=MISSING'; exit 2; }
[[ -f "$URL_FILE" ]] || { echo 'PUBLIC_BRIDGE_URL=MISSING'; exit 2; }
command -v gh >/dev/null 2>&1 || { echo 'GITHUB_CLI=MISSING'; exit 2; }

PUBLIC_URL="$(cat "$URL_FILE")"
[[ "$PUBLIC_URL" == https://* ]] || { echo 'PUBLIC_BRIDGE_URL=INVALID'; exit 2; }
curl -fsS --max-time 15 "$PUBLIC_URL/health" >/dev/null

ADAPTER_SHA="$(git rev-parse HEAD)"
PRIVATE_SHA="$(python3 - <<'PY'
import json
with open('ops/agent-lab/bridge/public-runner-target.json') as f:
    d=json.load(f)
s=d.get('hive_private_sha','')
if len(s)!=40 or any(c not in '0123456789abcdefABCDEF' for c in s):
    raise SystemExit(2)
print(s)
PY
)"

# Do not expose any bearer token. The workflow receives only the public bridge
# URL; the stable bearer token remains in the protected Actions environment.
gh workflow run "$WORKFLOW" \
  -R "$REPO" \
  --ref main \
  -f adapter_sha="$ADAPTER_SHA" \
  -f hive_private_sha="$PRIVATE_SHA" \
  -f bridge_url="$PUBLIC_URL"

echo 'QUEEN_PUBLIC_RUNNER_DISPATCH=CREATED'
echo "ADAPTER_SHA=$ADAPTER_SHA"
echo "HIVE_PRIVATE_SHA=$PRIVATE_SHA"
echo 'TOKEN_EXPOSED=false'
