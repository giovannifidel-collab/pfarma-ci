#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PROFILE="${KIMI_LAB_PROFILE_DIR:-$HOME/.hive-agent-lab/kimi-profile}"
PORT="${KIMI_LAB_CDP_PORT:-9223}"
SHARED_HOST="$ROOT/../browser-host/ensure-desktop.sh"
mkdir -p "$PROFILE"

ensure_kimi_target(){
  local list
  list="$(curl -fsS "http://127.0.0.1:${PORT}/json/list" 2>/dev/null || true)"
  if printf '%s' "$list" | grep -Eiq 'https?://[^" ]*(kimi\.com|kimi\.ai|moonshot)'; then
    return 0
  fi
  curl -fsS -X PUT "http://127.0.0.1:${PORT}/json/new?https%3A%2F%2Fwww.kimi.com%2F" >/dev/null 2>&1 || true
  for _ in $(seq 1 20); do
    sleep .25
    list="$(curl -fsS "http://127.0.0.1:${PORT}/json/list" 2>/dev/null || true)"
    if printf '%s' "$list" | grep -Eiq 'https?://[^" ]*(kimi\.com|kimi\.ai|moonshot)'; then
      return 0
    fi
  done
  return 1
}

if curl -fsS "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
  ensure_kimi_target || true
  echo "KIMI LAB BROWSER READY"
  echo "CDP=http://127.0.0.1:${PORT}"
  echo "PROFILE=$PROFILE"
  exit 0
fi

if [[ ! -S /tmp/.X11-unix/X1 ]]; then bash "$SHARED_HOST"; fi
export DISPLAY=:1

find_browser(){
  if [[ -n "${KIMI_LAB_BROWSER_BIN:-}" && -x "${KIMI_LAB_BROWSER_BIN}" ]]; then printf '%s\n' "$KIMI_LAB_BROWSER_BIN"; return; fi
  for b in google-chrome-stable google-chrome chromium chromium-browser; do command -v "$b" >/dev/null 2>&1 && { command -v "$b"; return; }; done
  local p
  p="$(find "$HOME/.cache/ms-playwright" -type f -path '*/chrome-linux*/chrome' -perm -u+x 2>/dev/null | head -n1 || true)"
  [[ -n "$p" ]] && printf '%s\n' "$p"
}
BROWSER="$(find_browser || true)"
[[ -n "$BROWSER" ]] || { echo "ERROR: Chromium non disponibile"; exit 1; }

nohup "$BROWSER" \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port="$PORT" \
  --user-data-dir="$PROFILE" --disk-cache-size=134217728 --media-cache-size=33554432 \
  --no-first-run --no-default-browser-check --disable-dev-shm-usage --no-sandbox \
  "https://www.kimi.com/" >"$PROFILE/chrome.log" 2>&1 &
echo $! >"$PROFILE/chrome.pid"

for _ in $(seq 1 75); do
  if curl -fsS "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
    ensure_kimi_target || true
    echo "KIMI LAB BROWSER READY"
    echo "CDP=http://127.0.0.1:${PORT}"
    echo "PROFILE=$PROFILE"
    echo "If this fallback profile is not authenticated, use the private noVNC desktop once; never paste credentials in the terminal."
    exit 0
  fi
  sleep .4
done

echo "ERROR: Kimi Chromium avviato ma CDP non raggiungibile"
tail -n 40 "$PROFILE/chrome.log" 2>/dev/null || true
exit 1
