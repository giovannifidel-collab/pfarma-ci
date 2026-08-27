#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SKILL_SRC="$REPO_ROOT/hive-agent-skill/SKILL.md"
SKILL_DIR="$HOME/.openclaw/workspace/skills/hive-agent"
OPENCLAW="$HOME/.local/bin/openclaw"

mkdir -p "$SKILL_DIR"
cp "$SKILL_SRC" "$SKILL_DIR/SKILL.md"

if [[ ! -x "$OPENCLAW" ]]; then
  echo "openclaw missing at $OPENCLAW" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git missing" >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh missing" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI is not authenticated" >&2
  exit 1
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
printf 'HIVE Skill: %s\n' "$SKILL_DIR/SKILL.md"
printf 'Kimi plugin: configured\n'
printf 'Gateway: healthy\n'
printf 'Repository: %s\n' "$(git remote get-url origin 2>/dev/null || echo unknown)"
printf 'Branch: %s\n' "$(git branch --show-current)"
printf '\nNEXT: in the linked Kimi/OpenClaw conversation, send exactly: HIVE SYNC HIVE-KIMI-0001\n'
