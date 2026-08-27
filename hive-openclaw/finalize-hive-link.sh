#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SKILL_SRC="$REPO_ROOT/hive-agent-skill/SKILL.md"
SKILL_DIR="$HOME/.openclaw/workspace/skills/hive-agent"
OPENCLAW="$HOME/.local/bin/openclaw"
LOCAL_BIN="$HOME/.local/bin"

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
# GH_TOKEN, so map it without printing the value. No token is written to disk
# by this script.
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

if ! "$OPENCLAW" gateway status >/dev/null 2>&1; then
  echo "OpenClaw gateway is not healthy" >&2
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
printf 'Repository: %s\n' "$(git remote get-url origin 2>/dev/null || echo unknown)"
printf 'Branch: %s\n' "$(git branch --show-current)"

if [[ "$GH_AUTH" == "needs_browser_login" ]]; then
  printf '\nACTION REQUIRED: run `gh auth login --web --git-protocol https` in this Codespace.\n'
  printf 'Authorize GitHub in the browser, then rerun this script. Do not paste tokens in chat.\n'
  exit 2
fi

printf '\nNEXT: in the linked Kimi/OpenClaw conversation, send exactly: HIVE SYNC HIVE-KIMI-0001\n'
