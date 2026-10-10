#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/workspaces/pfarma-ci"
BRANCH="hive-cloud-computer-v0"
PRIVATE_REPO="giovannifidel-collab/hive-alveare"

cd "$ROOT"
command -v git >/dev/null 2>&1 || { echo 'ERROR: git missing'; exit 90; }
REAL_GH="$(command -v gh || true)"
[[ -n "$REAL_GH" ]] || { echo 'ERROR: GitHub CLI missing'; exit 91; }

hive_user_gh(){ env -u GH_TOKEN -u GITHUB_TOKEN "$REAL_GH" "$@"; }
private_access_ok(){
  hive_user_gh auth status -h github.com >/dev/null 2>&1 &&
  hive_user_gh api "repos/${PRIVATE_REPO}" >/dev/null 2>&1
}

if ! private_access_ok; then
  echo
  echo '=== ONE-TIME PRIVATE HIVE GITHUB AUTHORIZATION ==='
  hive_user_gh auth login -h github.com -p https -w -s repo,workflow
fi
private_access_ok || { echo 'ERROR: private HIVE GitHub access unavailable'; exit 94; }
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

git fetch origin "$BRANCH"
CURRENT="$(git branch --show-current)"
if [[ "$CURRENT" != "$BRANCH" ]]; then
  [[ -z "$(git status --porcelain)" ]] || { echo 'ERROR: working tree has local changes; refusing branch switch'; exit 93; }
  git switch "$BRANCH"
fi
git merge --ff-only FETCH_HEAD

echo 'DEGRADED_FINALIZE_ENTRYPOINT=READY'
set +e
bash ops/agent-lab/bridge/finalize-queen-integration-degraded.sh
RC=$?
set -e

if [[ "$RC" -eq 0 ]]; then
  echo 'ENTRYPOINT_RESULT=HIVE_INTEGRATED_DEGRADED'
else
  echo 'ENTRYPOINT_RESULT=BLOCKED'
  echo "ENTRYPOINT_EXIT_CODE=$RC"
fi
exit "$RC"
