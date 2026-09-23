#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PROFILE="${DEEPSEEK_LAB_PROFILE_DIR:-$HOME/.hive-agent-lab/deepseek-profile}"
PORT="${DEEPSEEK_LAB_CDP_PORT:-9227}"
DISK_CACHE_BYTES="${DEEPSEEK_LAB_DISK_CACHE_BYTES:-134217728}"
MEDIA_CACHE_BYTES="${DEEPSEEK_LAB_MEDIA_CACHE_BYTES:-33554432}"
SHARED_HOST="$ROOT/../browser-host/ensure-desktop.sh"
mkdir -p "$PROFILE"

playwright_browser(){
  [[ -d node_modules/playwright ]] || return 1
  local candidate
  candidate="$(node --input-type=module -e "import { chromium } from 'playwright'; process.stdout.write(chromium.executablePath())" 2>/dev/null || true)"
  if [[ -n "$candidate" && -x "$candidate" ]]; then printf '%s\n' "$candidate"; return 0; fi
  return 1
}

find_browser(){
  if [[ -n "${DEEPSEEK_LAB_BROWSER_BIN:-}" && -x "${DEEPSEEK_LAB_BROWSER_BIN}" ]]; then printf '%s\n' "$DEEPSEEK_LAB_BROWSER_BIN"; return 0; fi
  for bin in google-chrome-stable google-chrome chromium chromium-browser; do
    if command -v "$bin" >/dev/null 2>&1; then command -v "$bin"; return 0; fi
  done
  playwright_browser && return 0
  return 1
}

if curl -fsS "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
  echo "DEEPSEEK LAB BROWSER READY"
  echo "CDP=http://127.0.0.1:${PORT}"
  echo "PROFILE=$PROFILE"
  exit 0
fi

if [[ ! -d node_modules/playwright ]]; then
  echo "DEEPSEEK LAB: installazione dipendenze Node..."
  npm install
fi

BROWSER="$(find_browser || true)"
if [[ -z "$BROWSER" ]]; then
  echo "DEEPSEEK LAB: Chromium non presente; bootstrap Playwright Chromium..."
  npx playwright install chromium
  BROWSER="$(find_browser || true)"
fi
if [[ -z "$BROWSER" ]]; then echo "ERROR: Chromium non disponibile."; exit 1; fi

if [[ ! -S "/tmp/.X11-unix/X1" ]]; then
  if [[ ! -f "$SHARED_HOST" ]]; then echo "ERROR: shared Agent Lab browser host missing: $SHARED_HOST"; exit 3; fi
  bash "$SHARED_HOST"
fi
export DISPLAY=":1"

rm -rf "$PROFILE/Default/Cache" "$PROFILE/Default/Code Cache" "$PROFILE/Default/GPUCache" "$PROFILE/ShaderCache" "$PROFILE/GrShaderCache" 2>/dev/null || true

nohup "$BROWSER" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port="$PORT" \
  --user-data-dir="$PROFILE" \
  --disk-cache-size="$DISK_CACHE_BYTES" \
  --media-cache-size="$MEDIA_CACHE_BYTES" \
  --no-first-run \
  --no-default-browser-check \
  --disable-dev-shm-usage \
  --no-sandbox \
  "https://chat.deepseek.com/" \
  >"$PROFILE/chrome.log" 2>&1 &

echo $! > "$PROFILE/chrome.pid"
for _ in $(seq 1 75); do
  if curl -fsS "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
    echo "DEEPSEEK LAB BROWSER READY"
    echo "CDP=http://127.0.0.1:${PORT}"
    echo "PROFILE=$PROFILE"
    echo "CACHE_CAP=$((DISK_CACHE_BYTES/1024/1024))MiB disk + $((MEDIA_CACHE_BYTES/1024/1024))MiB media"
    if [[ -n "${CODESPACE_NAME:-}" && -n "${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-}" ]]; then
      echo "Open this authenticated Codespaces URL:"
      echo "https://${CODESPACE_NAME}-6080.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}/vnc.html?autoconnect=true&resize=scale"
    fi
    echo "Accedi a DeepSeek manualmente una sola volta se richiesto; non inserire credenziali nel terminale."
    exit 0
  fi
  sleep 0.4
done

echo "ERROR: Chromium avviato ma CDP non raggiungibile."
tail -n 40 "$PROFILE/chrome.log" 2>/dev/null || true
exit 1
