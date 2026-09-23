#!/usr/bin/env bash
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_ROOT/.." && pwd)"
CF_CONFIG="$REPO_ROOT/hive-kimi-cloudflare-worker/wrangler.toml"
PROFILE_KEY="session:kimi:chromium-profile-tgz-b64"
ROOT="$(mktemp -d)"
PROFILE="$ROOT/chrome-profile"
ARCHIVE="$ROOT/kimi-chromium-profile.tar.gz"
PAYLOAD="$ROOT/kimi-chromium-profile.tar.gz.b64"
DISPLAY_NUM=99
DISPLAY=":$DISPLAY_NUM"
NOVNC_PORT=6080
CDP_PORT=9222

cleanup() {
  set +e
  [[ -n "${CHROME_PID:-}" ]] && kill "$CHROME_PID" 2>/dev/null || true
  [[ -n "${NOVNC_PID:-}" ]] && kill "$NOVNC_PID" 2>/dev/null || true
  [[ -n "${VNC_PID:-}" ]] && kill "$VNC_PID" 2>/dev/null || true
  [[ -n "${XVFB_PID:-}" ]] && kill "$XVFB_PID" 2>/dev/null || true
  sleep 1
  rm -rf "$ROOT" 2>/dev/null || true
}
trap cleanup EXIT

if [[ ! -f "$CF_CONFIG" ]]; then
  echo "Cloudflare Worker config not found: $CF_CONFIG" >&2
  echo "Run: bash hive-kimi-cloudflare-worker/deploy.sh" >&2
  exit 2
fi

WRANGLER=(npx --yes wrangler@latest)
WHOAMI_LOG="$ROOT/wrangler-whoami.log"
set +e
"${WRANGLER[@]}" whoami --config "$CF_CONFIG" >"$WHOAMI_LOG" 2>&1
WHOAMI_STATUS=$?
set -e
if [[ "$WHOAMI_STATUS" -ne 0 ]] || grep -qiE 'not authenticated|please run .*wrangler login|login required' "$WHOAMI_LOG"; then
  cat "$WHOAMI_LOG"
  echo "Cloudflare Wrangler login required." >&2
  echo "Run: npx --yes wrangler@latest login --device --browser=false" >&2
  exit 2
fi

sudo apt-get update -qq
sudo apt-get install -y -qq xvfb x11vnc novnc websockify >/dev/null

mkdir -p "$ROOT/node"
cd "$ROOT/node"
npm init -y >/dev/null 2>&1
npm install playwright@1.55.0 >/dev/null 2>&1
npx playwright install --with-deps chromium >/dev/null

CHROME="$(node -e "const {chromium}=require('playwright'); process.stdout.write(chromium.executablePath())")"

Xvfb "$DISPLAY" -screen 0 1440x1000x24 -ac >"$ROOT/xvfb.log" 2>&1 &
XVFB_PID=$!
export DISPLAY
sleep 1

x11vnc -display "$DISPLAY" -nopw -forever -shared -rfbport 5900 >"$ROOT/x11vnc.log" 2>&1 &
VNC_PID=$!
websockify --web=/usr/share/novnc/ "$NOVNC_PORT" localhost:5900 >"$ROOT/novnc.log" 2>&1 &
NOVNC_PID=$!

mkdir -p "$PROFILE"
"$CHROME" \
  --no-sandbox \
  --disable-dev-shm-usage \
  --password-store=basic \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port="$CDP_PORT" \
  --user-data-dir="$PROFILE" \
  --window-size=1400,950 \
  'https://www.kimi.com/en' >"$ROOT/chrome.log" 2>&1 &
CHROME_PID=$!

sleep 3

if [[ -n "${CODESPACE_NAME:-}" ]]; then
  echo
  echo "KIMI FULL PROFILE LOGIN WINDOW READY"
  echo "Open this authenticated Codespaces URL in your normal browser:"
  echo "https://${CODESPACE_NAME}-${NOVNC_PORT}.app.github.dev/vnc.html?autoconnect=true&resize=scale"
else
  echo "Forward Codespaces port $NOVNC_PORT and open /vnc.html?autoconnect=true&resize=scale"
fi

echo
echo "Log in to Kimi in that cloud browser and verify that the chat UI is authenticated."
echo "Do NOT paste credentials into this terminal."
read -r -p "When Kimi is fully logged in, press ENTER here... " _

# Stop Chromium cleanly before archiving its user-data-dir.
kill "$CHROME_PID" 2>/dev/null || true
for _ in {1..20}; do
  if ! kill -0 "$CHROME_PID" 2>/dev/null; then break; fi
  sleep 0.5
done
kill -9 "$CHROME_PID" 2>/dev/null || true
unset CHROME_PID
sleep 1

# Remove process locks and disposable caches, but retain authentication databases,
# IndexedDB, Local Storage, Service Workers and browser metadata.
find "$PROFILE" -maxdepth 2 -type f \( -name 'SingletonLock' -o -name 'SingletonCookie' -o -name 'SingletonSocket' \) -delete 2>/dev/null || true
find "$PROFILE" -type d \( \
  -name 'Cache' -o -name 'Code Cache' -o -name 'GPUCache' -o -name 'DawnCache' -o \
  -name 'ShaderCache' -o -name 'GrShaderCache' -o -name 'GraphiteDawnCache' -o \
  -name 'Crashpad' -o -name 'BrowserMetrics' -o -name 'component_crx_cache' \
\) -prune -exec rm -rf {} + 2>/dev/null || true

# Archive the complete persistent profile. Paths are relative so the runner can
# restore it into a fresh Linux workspace.
tar -C "$PROFILE" -czf "$ARCHIVE" .
[[ -s "$ARCHIVE" ]] || { echo "Failed to archive Chromium profile" >&2; exit 1; }
base64 -w0 "$ARCHIVE" > "$PAYLOAD"
[[ -s "$PAYLOAD" ]] || { echo "Failed to encode Chromium profile" >&2; exit 1; }

ARCHIVE_BYTES="$(wc -c < "$ARCHIVE")"
PAYLOAD_BYTES="$(wc -c < "$PAYLOAD")"
echo "HIVE_KIMI_PROFILE_ARCHIVE_BYTES=$ARCHIVE_BYTES"
echo "HIVE_KIMI_PROFILE_PAYLOAD_BYTES=$PAYLOAD_BYTES"

# Workers KV values are capped at 25 MiB. Keep safety headroom for the base64 value.
if (( PAYLOAD_BYTES > 24000000 )); then
  echo "Kimi Chromium profile payload is too large for the current KV transport ($PAYLOAD_BYTES bytes)." >&2
  echo "Profile was not uploaded. We will need chunked/R2 storage instead." >&2
  exit 1
fi

"${WRANGLER[@]}" kv key put "$PROFILE_KEY" \
  --path "$PAYLOAD" \
  --binding HIVE_KIMI_RESULTS \
  --remote \
  --config "$CF_CONFIG" >/dev/null

echo
echo "HIVE KIMI FULL PROFILE BOOTSTRAP READY"
echo "Complete Chromium profile stored privately in HIVE Cloudflare KV."
echo "GitHub Actions secret required: NO"
echo "Kimi credentials/session data committed to GitHub: NO"
