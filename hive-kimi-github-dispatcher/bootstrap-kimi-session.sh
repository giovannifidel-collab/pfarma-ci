#!/usr/bin/env bash
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_ROOT/.." && pwd)"
CF_CONFIG="$REPO_ROOT/hive-kimi-cloudflare-worker/wrangler.toml"
SESSION_KEY="session:kimi:storage-state-gz-b64"
ROOT="$(mktemp -d)"
STATE="$ROOT/kimi-storage-state.json"
PAYLOAD="$ROOT/kimi-storage-state.json.gz.b64"
PROFILE="$ROOT/chrome-profile"
DISPLAY_NUM=99
DISPLAY=":$DISPLAY_NUM"
NOVNC_PORT=6080
CDP_PORT=9222

cleanup() {
  set +e
  [[ -n "${CHROME_PID:-}" ]] && kill "$CHROME_PID" 2>/dev/null
  [[ -n "${NOVNC_PID:-}" ]] && kill "$NOVNC_PID" 2>/dev/null
  [[ -n "${VNC_PID:-}" ]] && kill "$VNC_PID" 2>/dev/null
  [[ -n "${XVFB_PID:-}" ]] && kill "$XVFB_PID" 2>/dev/null
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
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port="$CDP_PORT" \
  --user-data-dir="$PROFILE" \
  --window-size=1400,950 \
  'https://www.kimi.com/' >"$ROOT/chrome.log" 2>&1 &
CHROME_PID=$!

sleep 3

if [[ -n "${CODESPACE_NAME:-}" ]]; then
  echo
  echo "KIMI LOGIN WINDOW READY"
  echo "Open this authenticated Codespaces URL in your normal browser:"
  echo "https://${CODESPACE_NAME}-${NOVNC_PORT}.app.github.dev/vnc.html?autoconnect=true&resize=scale"
else
  echo "Forward Codespaces port $NOVNC_PORT and open /vnc.html?autoconnect=true&resize=scale"
fi

echo
echo "Log in to Kimi in that cloud browser."
echo "Do NOT paste credentials into this terminal."
read -r -p "When Kimi is fully logged in and the chat UI is visible, press ENTER here... " _

cat > "$ROOT/node/export-state.mjs" <<'JS'
import { chromium } from 'playwright';
const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
const contexts = browser.contexts();
if (!contexts.length) throw new Error('No Chromium context found');
await contexts[0].storageState({ path: process.env.STATE_PATH, indexedDB: true });
await browser.close();
JS

STATE_PATH="$STATE" node "$ROOT/node/export-state.mjs"
[[ -s "$STATE" ]] || { echo "Failed to export Kimi browser state" >&2; exit 1; }

gzip -c "$STATE" | base64 -w0 > "$PAYLOAD"
[[ -s "$PAYLOAD" ]] || { echo "Failed to encode Kimi browser state" >&2; exit 1; }

# Store the authenticated browser state directly in the existing private
# Cloudflare KV namespace. GitHub Actions never needs a repository secret:
# it will lease this state from the Worker using GitHub OIDC at runtime.
"${WRANGLER[@]}" kv key put "$SESSION_KEY" \
  --path "$PAYLOAD" \
  --binding HIVE_KIMI_RESULTS \
  --remote \
  --config "$CF_CONFIG" >/dev/null

echo
echo "HIVE KIMI SESSION BOOTSTRAP READY"
echo "Kimi browser state stored privately in HIVE Cloudflare KV."
echo "GitHub Actions secret required: NO"
echo "Kimi credentials/session data committed to GitHub: NO"
