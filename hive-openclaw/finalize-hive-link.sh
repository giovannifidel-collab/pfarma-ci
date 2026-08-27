#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SKILL_SRC="$REPO_ROOT/hive-agent-skill/SKILL.md"
SKILL_DIR="$HOME/.openclaw/workspace/skills/hive-agent"
OPENCLAW="$HOME/.local/bin/openclaw"
LOCAL_BIN="$HOME/.local/bin"
OPENCLAW_PREFIX="$HOME/.openclaw"

mkdir -p "$SKILL_DIR" "$LOCAL_BIN"
cp "$SKILL_SRC" "$SKILL_DIR/SKILL.md"

if [[ ! -x "$OPENCLAW" ]]; then
  echo "openclaw missing at $OPENCLAW" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git missing" >&2
  exit 1
fi

# Resolve the embedded Node/npm runtime used by the pinned OpenClaw install.
NODE_BIN_DIR="$(for d in "$OPENCLAW_PREFIX"/tools/node-v*/bin; do [[ -x "$d/node" ]] && printf '%s\n' "$d"; done | sort -V | tail -n 1)"
if [[ -z "$NODE_BIN_DIR" || ! -x "$NODE_BIN_DIR/npm" ]]; then
  echo "OpenClaw embedded Node/npm runtime not found" >&2
  exit 1
fi
export PATH="$NODE_BIN_DIR:$LOCAL_BIN:$OPENCLAW_PREFIX/bin:$PATH"
hash -r

# OpenClaw 2026.4.2 has a published-package bug: dist imports grammy runtime
# packages that are missing from the npm dependency set. Repair the package in
# place, all in one npm transaction, so one install cannot remove another.
OPENCLAW_PKG="$NODE_BIN_DIR/../lib/node_modules/openclaw"
if [[ ! -d "$OPENCLAW_PKG" ]]; then
  echo "OpenClaw package root not found at $OPENCLAW_PKG" >&2
  exit 1
fi

NEED_GRAMMY_REPAIR=0
for pkg in grammy @grammyjs/runner @grammyjs/transformer-throttler; do
  if ! (cd "$OPENCLAW_PKG" && node -e "import('$pkg').catch(()=>process.exit(1))" >/dev/null 2>&1); then
    NEED_GRAMMY_REPAIR=1
  fi
done

if [[ "$NEED_GRAMMY_REPAIR" -eq 1 ]]; then
  echo "Repairing known OpenClaw 2026.4.2 grammy runtime dependency bug..."
  (
    cd "$OPENCLAW_PKG"
    npm install --no-save --no-audit --no-fund \
      grammy @grammyjs/runner@^2.0.3 @grammyjs/transformer-throttler@^1.2.1
  )
fi

for pkg in grammy @grammyjs/runner @grammyjs/transformer-throttler; do
  if ! (cd "$OPENCLAW_PKG" && node -e "import('$pkg').catch(()=>process.exit(1))" >/dev/null 2>&1); then
    echo "OpenClaw runtime dependency still missing after repair: $pkg" >&2
    exit 1
  fi
done

echo "OpenClaw grammy runtime: healthy"

# The custom HIVE Codespace image may not include GitHub CLI. Bootstrap it
# inside the cloud VM when needed; nothing is installed on the user's device.
if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI missing; installing it inside this Codespace..."
  if command -v sudo >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y gh
  else
    echo "Automatic gh installation is unavailable in this Codespace." >&2
    echo "Install GitHub CLI in the Codespace, then rerun this script." >&2
    exit 1
  fi
fi

# Codespaces can expose GITHUB_TOKEN to the environment. gh natively honors
# GH_TOKEN, so map it without printing the value. No token is written to disk.
if [[ -z "${GH_TOKEN:-}" && -n "${GITHUB_TOKEN:-}" ]]; then
  export GH_TOKEN="$GITHUB_TOKEN"
fi

GH_AUTH="authenticated"
if ! gh auth status >/dev/null 2>&1; then
  GH_AUTH="needs_browser_login"
fi

PLUGIN_OK=0
if "$OPENCLAW" config get plugins.entries.kimi-claw >/dev/null 2>&1; then
  PLUGIN_OK=1
fi

if [[ "$PLUGIN_OK" -ne 1 ]]; then
  echo "kimi-claw plugin configuration not found" >&2
  exit 1
fi

# Restart after runtime repair so the linked Kimi bridge reloads a clean module graph.
pkill -f 'openclaw gateway' >/dev/null 2>&1 || true
nohup "$OPENCLAW" gateway --bind loopback --port 18789 >/tmp/hive-openclaw-gateway.log 2>&1 &
sleep 3

if ! "$OPENCLAW" gateway status >/dev/null 2>&1; then
  echo "OpenClaw gateway is not healthy after runtime repair" >&2
  tail -n 80 /tmp/hive-openclaw-gateway.log >&2 || true
  exit 1
fi

printf '\nHIVE OPENCLAW LINK READY\n'
printf 'OpenClaw: '
"$OPENCLAW" --version
printf 'Git: '
git --version
printf 'GitHub CLI: '
gh --version | head -n 1
printf 'GitHub auth: %s\n' "$GH_AUTH"
printf 'HIVE Skill: %s\n' "$SKILL_DIR/SKILL.md"
printf 'Kimi plugin: configured\n'
printf 'Gateway: healthy\n'
printf 'Runtime deps: grammy healthy\n'
printf 'Repository: %s\n' "$(git remote get-url origin 2>/dev/null || echo unknown)"
printf 'Branch: %s\n' "$(git branch --show-current)"

if [[ "$GH_AUTH" == "needs_browser_login" ]]; then
  printf '\nACTION REQUIRED: run `gh auth login --web --git-protocol https` in this Codespace.\n'
  printf 'Authorize GitHub in the browser, then rerun this script. Do not paste tokens in chat.\n'
  exit 2
fi

printf '\nNEXT: in the linked Kimi/OpenClaw conversation, test /ping first. If it answers, send: HIVE SYNC HIVE-KIMI-0001\n'
