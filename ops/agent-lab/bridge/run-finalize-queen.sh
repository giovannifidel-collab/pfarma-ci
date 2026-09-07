#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/workspaces/pfarma-ci"
BRANCH="hive-cloud-computer-v0"
PRIVATE_REPO="giovannifidel-collab/hive-alveare"
AUTONOMOUS_MARKER="ops/agent-lab/bridge/AUTONOMOUS_PUBLIC_RUNNER"
ENDPOINT_FILE="ops/agent-lab/bridge/runtime-public-endpoint.json"

cd "$ROOT"
command -v git >/dev/null 2>&1 || { echo 'ERROR: git missing'; exit 90; }
REAL_GH="$(command -v gh || true)"
[[ -n "$REAL_GH" ]] || { echo 'ERROR: GitHub CLI missing'; exit 91; }

# Bring the local workspace to the authoritative adapter branch first. This is
# deliberately independent from private-HIVE authentication so an automatically
# restarted Codespace can recover connectivity without an interactive login.
git fetch origin "$BRANCH"
CURRENT="$(git branch --show-current)"
if [[ "$CURRENT" != "$BRANCH" ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: working tree has local changes on ${CURRENT:-detached}; refusing automatic branch switch" >&2
    exit 93
  fi
  git switch "$BRANCH"
fi
git pull --ff-only origin "$BRANCH"

# Autonomous public-runner takeover. The strict 10/10 finalizer below remains
# unchanged and can still be invoked explicitly with HIVE_STRICT_10=1. In the
# normal recovery path we only restore Tailscale + the bearer-protected bridge,
# publish its non-secret endpoint, and leave certification to the public runner.
if [[ -f "$AUTONOMOUS_MARKER" && "${HIVE_STRICT_10:-0}" != "1" ]]; then
  echo 'QUEEN_CONTROL_PLANE=AUTONOMOUS_PUBLIC_RUNNER'
  bash ops/agent-lab/bridge/ensure-tailscale.sh >/tmp/hive-ensure-tailscale.log 2>&1 || true
  HIVE_SKIP_SECRET_SYNC=1 bash ops/agent-lab/bridge/start-secure-tunnel.sh

  PUBLIC_URL="$(cat "$HOME/.hive-agent-lab/agent-bridge/url")"
  [[ "$PUBLIC_URL" == https://* ]] || { echo 'ERROR: invalid public bridge URL' >&2; exit 95; }
  curl -fsS --max-time 10 "$PUBLIC_URL/health" >/dev/null
  ADAPTER_SHA="$(git rev-parse HEAD)"

  python3 - "$PUBLIC_URL" "$ADAPTER_SHA" >"$ENDPOINT_FILE" <<'PY'
import json, sys
print(json.dumps({"url": sys.argv[1], "adapter_sha": sys.argv[2], "token_exposed": False}, indent=2, sort_keys=True))
PY

  git config user.name 'HIVE Codespace Bridge'
  git config user.email 'hive-bridge@users.noreply.github.com'
  git add "$ENDPOINT_FILE"
  if git diff --cached --quiet; then
    echo 'PUBLIC_BRIDGE_ENDPOINT_ALREADY_CURRENT=true'
  else
    git commit -m 'chore(hive): publish live Queen bridge endpoint'
    git push origin "HEAD:${BRANCH}"
  fi

  echo 'PUBLIC_BRIDGE_ENDPOINT=PUBLISHED'
  echo "ADAPTER_SHA=$ADAPTER_SHA"
  echo 'TOKEN_EXPOSED=false'
  echo 'ENTRYPOINT_RESULT=PUBLIC_BRIDGE_READY'
  exit 0
fi

# Strict 10/10 path preserved for explicit use. GitHub Codespaces may inject a
# repository-scoped token, so private-HIVE operations deliberately use the
# persistent user GitHub CLI credential.
hive_user_gh(){ env -u GH_TOKEN -u GITHUB_TOKEN "$REAL_GH" "$@"; }

private_access_ok(){
  hive_user_gh auth status -h github.com >/dev/null 2>&1 &&
  hive_user_gh api "repos/${PRIVATE_REPO}" >/dev/null 2>&1
}

if ! private_access_ok; then
  echo
  echo '=== ONE-TIME PRIVATE HIVE GITHUB AUTHORIZATION ==='
  echo 'The automatic Codespaces token cannot access hive-alveare.'
  echo 'Complete the GitHub web authorization shown by gh; this is stored in the Codespace credential store, not in the repository.'
  echo
  hive_user_gh auth login -h github.com -p https -w -s repo,workflow
fi

if ! private_access_ok; then
  echo 'ERROR: GitHub CLI user credential still cannot access giovannifidel-collab/hive-alveare.' >&2
  echo 'No TEST B, registry promotion, secret synchronization or Queen integration was attempted.' >&2
  exit 94
fi

echo 'PRIVATE_HIVE_GITHUB_AUTH=READY'

WRAPDIR="$(mktemp -d)"
cleanup(){ rm -rf "$WRAPDIR"; }
trap cleanup EXIT
cat >"$WRAPDIR/gh" <<EOF
#!/usr/bin/env bash
exec env -u GH_TOKEN -u GITHUB_TOKEN "$REAL_GH" "\$@"
EOF
chmod 700 "$WRAPDIR/gh"
export PATH="$WRAPDIR:$PATH"

echo 'FINALIZE_ENTRYPOINT=READY'
set +e
bash ops/agent-lab/bridge/finalize-queen-integration.sh
RC=$?
set -e

if [[ "$RC" -eq 0 ]]; then
  echo 'ENTRYPOINT_RESULT=HIVE_INTEGRATED'
else
  echo 'ENTRYPOINT_RESULT=BLOCKED'
  echo "ENTRYPOINT_EXIT_CODE=$RC"
fi
exit "$RC"
