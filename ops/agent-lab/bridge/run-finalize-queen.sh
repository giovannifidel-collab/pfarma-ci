#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/workspaces/pfarma-ci"
BRANCH="hive-cloud-computer-v0"
PRIVATE_REPO="giovannifidel-collab/hive-alveare"

cd "$ROOT"
command -v git >/dev/null 2>&1 || { echo 'ERROR: git missing'; exit 90; }
REAL_GH="$(command -v gh || true)"
[[ -n "$REAL_GH" ]] || { echo 'ERROR: GitHub CLI missing'; exit 91; }

# GitHub Codespaces may inject a repository-scoped GH_TOKEN/GITHUB_TOKEN.
# Those tokens can access pfarma-ci but may return 404 for the private HIVE
# control-plane repository. For HIVE-private operations we deliberately use
# the user's persistent GitHub CLI credential instead.
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

# Put a temporary gh shim first in PATH so every gh invocation made by the
# downstream supervisor ignores the Codespaces repo-scoped environment token
# and uses the persistent user credential verified above.
WRAPDIR="$(mktemp -d)"
cleanup(){ rm -rf "$WRAPDIR"; }
trap cleanup EXIT
cat >"$WRAPDIR/gh" <<EOF
#!/usr/bin/env bash
exec env -u GH_TOKEN -u GITHUB_TOKEN "$REAL_GH" "\$@"
EOF
chmod 700 "$WRAPDIR/gh"
export PATH="$WRAPDIR:$PATH"

# Bring the local workspace to the authoritative adapter branch without
# destroying local work. Refuse an automatic switch only when local changes
# would make it unsafe.
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
