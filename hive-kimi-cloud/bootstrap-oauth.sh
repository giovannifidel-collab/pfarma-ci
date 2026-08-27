#!/usr/bin/env bash
set -euo pipefail

export KIMI_CODE_HOME="${KIMI_CODE_HOME:-$HOME/.kimi-code}"
mkdir -p "$KIMI_CODE_HOME"

printf '\n=== HIVE KIMI CLOUD BOOTSTRAP ===\n'
printf '1) Kimi will print a verification URL and one-time device code.\n'
printf '2) Open that URL in your browser and authorize Kimi Code.\n'
printf '3) This script will then seal the resulting OAuth state into a GitHub Actions secret.\n\n'

kimi login

printf '\nChecking Kimi managed login...\n'
if ! find "$KIMI_CODE_HOME/credentials" -type f -name '*.json' -print -quit 2>/dev/null | grep -q .; then
  echo 'Kimi OAuth credentials were not created.' >&2
  exit 1
fi

repo="${GITHUB_REPOSITORY:-giovannifidel-collab/pfarma-ci}"
secret_name='HIVE_KIMI_CODE_HOME_B64'

# Codespaces normally supplies GitHub CLI auth. If that token cannot manage
# Actions secrets, fall back to the official GitHub CLI web OAuth flow.
if ! gh secret list --repo "$repo" >/dev/null 2>&1; then
  echo
  echo 'GitHub needs a one-time browser authorization to store the encrypted secret.'
  unset GH_TOKEN GITHUB_TOKEN || true
  gh auth login --hostname github.com --web --git-protocol https --scopes repo,workflow
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/kimi-code"

if test -f "$KIMI_CODE_HOME/config.toml"; then
  cp "$KIMI_CODE_HOME/config.toml" "$tmp/kimi-code/config.toml"
fi
cp -a "$KIMI_CODE_HOME/credentials" "$tmp/kimi-code/credentials"

# Secret body is streamed directly to GitHub; it is never committed or printed.
tar -C "$tmp" -czf - kimi-code | base64 -w0 | gh secret set "$secret_name" --repo "$repo" --body -

printf '\nKimi OAuth state stored as encrypted GitHub Actions secret: %s\n' "$secret_name"
printf 'No credential was committed to the repository.\n'
printf 'Bootstrap complete. You may stop/delete this Codespace.\n'
