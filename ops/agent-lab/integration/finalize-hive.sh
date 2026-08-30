#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(git -C "$HERE" rev-parse --show-toplevel)"
cd "$ROOT"

BRANCH="$(git branch --show-current)"
if [[ "$BRANCH" != "hive-cloud-computer-v0" ]]; then
  echo "ERROR: expected branch hive-cloud-computer-v0, got ${BRANCH:-detached}"
  exit 2
fi

STANDARD_DIR="ops/agent-lab/standard"
INTEGRATION_DIR="ops/agent-lab/integration"

echo "=== HIVE / QUEEN AUTONOMOUS FINALIZER ==="
echo "BRANCH=$BRANCH"
echo "POLICY=fail-closed"
echo

echo "[1/6] Runtime standardization with bounded self-healing"
bash "$STANDARD_DIR/standardize-all.sh" --attempts 3

echo
echo "[2/6] Promote proof to C_STANDARDIZED"
node "$INTEGRATION_DIR/promote-registry.mjs" --stage standardized --report "$STANDARD_DIR/reports/latest.json"
node "$STANDARD_DIR/validate-static.mjs"

echo
echo "[3/6] Enter D_HIVE_INTEGRATION"
node "$INTEGRATION_DIR/promote-registry.mjs" --stage begin-integration
node "$STANDARD_DIR/validate-static.mjs"

echo
echo "[4/6] Queen -> 10 agents end-to-end gate"
node "$INTEGRATION_DIR/integration-test.mjs" --attempts 3 --semantic-attempts 2

echo
echo "[5/6] Promote proof to E_HIVE_INTEGRATED"
node "$INTEGRATION_DIR/promote-registry.mjs" --stage integrated --report "$INTEGRATION_DIR/reports/latest.json"
node "$STANDARD_DIR/validate-static.mjs"

echo
echo "[6/6] Seal durable registry/proof state"
git add "$STANDARD_DIR/registry.json" "$STANDARD_DIR/proof-lock.json"
if ! git diff --cached --quiet; then
  git -c user.name='HIVE Queen' -c user.email='hive-queen@users.noreply.github.com' \
    commit -m 'feat(hive): seal Queen 10-agent integration proof'
  git push origin HEAD:hive-cloud-computer-v0
else
  echo "STATE_ALREADY_SEALED=true"
fi

echo
echo "=== HIVE / QUEEN FINALIZATION COMPLETE ==="
echo "STANDARDIZED=10/10"
echo "HIVE_INTEGRATED=10/10"
echo "QUEEN_AGENT_FABRIC=READY"
echo "FAIL_CLOSED=true"
