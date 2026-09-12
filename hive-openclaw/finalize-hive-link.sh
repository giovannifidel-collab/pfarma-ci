#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SKILL_SRC="$REPO_ROOT/hive-agent-skill/SKILL.md"
SKILL_DIR="$HOME/.openclaw/workspace/skills/hive-agent"
OPENCLAW="$HOME/.local/bin/openclaw"
LOCAL_BIN="$HOME/.local/bin"
OPENCLAW_PREFIX="$HOME/.openclaw"
GATEWAY_LOG="/tmp/hive-openclaw-gateway.log"
GATEWAY_PORT=18789

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

NODE_BIN_DIR="$(for d in "$OPENCLAW_PREFIX"/tools/node-v*/bin; do [[ -x "$d/node" ]] && printf '%s\n' "$d"; done | sort -V | tail -n 1)"
if [[ -z "$NODE_BIN_DIR" || ! -x "$NODE_BIN_DIR/npm" ]]; then
  echo "OpenClaw embedded Node/npm runtime not found" >&2
  exit 1
fi
export PATH="$NODE_BIN_DIR:$LOCAL_BIN:$OPENCLAW_PREFIX/bin:$PATH"
hash -r

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

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI missing; installing it inside this Codespace..."
  if command -v sudo >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y gh
  else
    echo "Automatic gh installation is unavailable in this Codespace." >&2
    exit 1
  fi
fi

if [[ -z "${GH_TOKEN:-}" && -n "${GITHUB_TOKEN:-}" ]]; then
  export GH_TOKEN="$GITHUB_TOKEN"
fi

GH_AUTH="authenticated"
if ! gh auth status >/dev/null 2>&1; then
  GH_AUTH="needs_browser_login"
fi

if ! "$OPENCLAW" config get plugins.entries.kimi-claw >/dev/null 2>&1; then
  echo "kimi-claw plugin configuration not found" >&2
  exit 1
fi

echo "Stopping any existing OpenClaw gateway..."
"$OPENCLAW" gateway stop >/dev/null 2>&1 || true
sleep 1

# Kill any process that actually owns the gateway port, regardless of its
# process name. This avoids stale daemons such as `openclaw-gatewa` that pgrep
# can miss because Linux truncates the comm field.
LISTENER_PIDS=""
if command -v ss >/dev/null 2>&1; then
  LISTENER_PIDS="$(ss -ltnp "( sport = :$GATEWAY_PORT )" 2>/dev/null | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | sort -u | tr '\n' ' ')"
fi
if [[ -z "$LISTENER_PIDS" ]] && command -v fuser >/dev/null 2>&1; then
  LISTENER_PIDS="$(fuser -n tcp "$GATEWAY_PORT" 2>/dev/null | tr '\n' ' ' || true)"
fi

if [[ -n "${LISTENER_PIDS// /}" ]]; then
  echo "Terminating listener(s) on port $GATEWAY_PORT: $LISTENER_PIDS"
  kill -TERM $LISTENER_PIDS >/dev/null 2>&1 || true
  sleep 1
fi

LISTENER_PIDS=""
if command -v ss >/dev/null 2>&1; then
  LISTENER_PIDS="$(ss -ltnp "( sport = :$GATEWAY_PORT )" 2>/dev/null | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | sort -u | tr '\n' ' ')"
fi
if [[ -n "${LISTENER_PIDS// /}" ]]; then
  echo "Force-killing listener(s) on port $GATEWAY_PORT: $LISTENER_PIDS"
  kill -KILL $LISTENER_PIDS >/dev/null 2>&1 || true
  sleep 1
fi

if command -v ss >/dev/null 2>&1 && ss -ltn "( sport = :$GATEWAY_PORT )" 2>/dev/null | grep -q ":$GATEWAY_PORT"; then
  echo "Port $GATEWAY_PORT is still occupied after forced shutdown" >&2
  ss -ltnp "( sport = :$GATEWAY_PORT )" >&2 || true
  exit 1
fi

echo "Port $GATEWAY_PORT is free. Starting fresh gateway..."
: >"$GATEWAY_LOG"
nohup "$OPENCLAW" gateway --bind loopback --port "$GATEWAY_PORT" >"$GATEWAY_LOG" 2>&1 &
NEW_GATEWAY_PID=$!

for _ in {1..40}; do
  if "$OPENCLAW" gateway status >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! "$OPENCLAW" gateway status >/dev/null 2>&1; then
  echo "OpenClaw gateway is not healthy after clean restart" >&2
  tail -n 120 "$GATEWAY_LOG" >&2 || true
  exit 1
fi

ACTUAL_GATEWAY_PID=""
if command -v ss >/dev/null 2>&1; then
  ACTUAL_GATEWAY_PID="$(ss -ltnp "( sport = :$GATEWAY_PORT )" 2>/dev/null | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | head -n 1)"
fi
[[ -n "$ACTUAL_GATEWAY_PID" ]] || ACTUAL_GATEWAY_PID="$NEW_GATEWAY_PID"

echo "Fresh gateway started: pid=$ACTUAL_GATEWAY_PID"

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
printf 'Gateway: healthy (pid=%s)\n' "$ACTUAL_GATEWAY_PID"
printf 'Runtime deps: grammy healthy\n'
printf 'Repository: %s\n' "$(git remote get-url origin 2>/dev/null || echo unknown)"
printf 'Branch: %s\n' "$(git branch --show-current)"

if [[ "$GH_AUTH" == "needs_browser_login" ]]; then
  printf '\nACTION REQUIRED: run `gh auth login --web --git-protocol https` in this Codespace.\n'
  exit 2
fi

printf '\nNEXT: test /ping in the linked Kimi/OpenClaw conversation. If it answers, send: HIVE SYNC HIVE-KIMI-0001\n'
