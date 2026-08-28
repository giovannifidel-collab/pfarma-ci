#!/usr/bin/env bash
set -euo pipefail

TARGET_REPO="giovannifidel-collab/hive-kimi-dispatcher"
ROOT="$(mktemp -d)"
STATE="$ROOT/kimi-storage-state.json"
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
  rm -rf "$ROOT"
}
trap cleanup EXIT

command -v gh >/dev/null || { echo "gh CLI required" >&2; exit 2; }
gh auth status >/dev/null
gh repo view "$TARGET_REPO" >/dev/null || { echo "Create $TARGET_REPO first" >&2; exit 2; }

sudo apt-get update -qq
sudo apt-get install -y -qq xvfb x11vnc novnc websockify >/dev/null

mkdir -p "$ROOT/node"
cd "$ROOT/node"
npm init -y >/dev/null 2>&1
npm install playwright@1.55.0 >/dev/null 2>&1
npx playwright install --with-deps chromium >/dev/null

CHROME="$(node -e "const {chromium}=require('playwright'); process.stdout.write(chromium.executablePath())")"

Xvfb "$DISPLAY" -screen 0 1440x1000x24 -ac >/tmp/hive-kimi-xvfb.log 2>&1 &
XVFB_PID=$!
export DISPLAY
sleep 1

x11vnc -display "$DISPLAY" -nopw -forever -shared -rfbport 5900 >/tmp/hive-kimi-x11vnc.log 2>&1 &
VNC_PID=$!
websockify --web=/usr/share/novnc/ "$NOVNC_PORT" localhost:5900 >/tmp/hive-kimi-novnc.log 2>&1 &
NOVNC_PID=$!

mkdir -p "$PROFILE"
"$CHROME" \
  --no-sandbox \
  --disable-dev-shm-usage \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port="$CDP_PORT" \
  --user-data-dir="$PROFILE" \
  --window-size=1400,950 \
  'https://www.kimi.com/' >/tmp/hive-kimi-chrome.log 2>&1 &
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

ENCODED_SIZE="$(gzip -c "$STATE" | base64 -w0 | wc -c)"
if (( ENCODED_SIZE > 48000 )); then
  echo "Compressed Kimi storage state is too large for a GitHub Actions secret ($ENCODED_SIZE bytes)." >&2
  exit 1
fi

gzip -c "$STATE" | base64 -w0 | gh secret set KIMI_STORAGE_STATE_GZ_B64 --repo "$TARGET_REPO"

echo
echo "HIVE KIMI SESSION BOOTSTRAP READY"
echo "Secret KIMI_STORAGE_STATE_GZ_B64 stored in $TARGET_REPO."
echo "No Kimi session data was committed to GitHub."
