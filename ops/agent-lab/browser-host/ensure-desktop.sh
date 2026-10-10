#!/usr/bin/env bash
set -euo pipefail

DISPLAY_NUM="${HIVE_AGENTLAB_DISPLAY_NUM:-1}"
DISPLAY_VALUE=":${DISPLAY_NUM}"
VNC_PORT="${HIVE_AGENTLAB_VNC_PORT:-5901}"
WEB_PORT="${HIVE_AGENTLAB_WEB_PORT:-6080}"
ROOT="${HIVE_AGENTLAB_HOST_DIR:-$HOME/.hive-agent-lab/browser-host}"
VNC_PASSWORD_FILE="$ROOT/vnc.pass"
VNC_PASSWORD_TEXT="$ROOT/vnc.password"
mkdir -p "$ROOT"
chmod 700 "$ROOT" 2>/dev/null || true

port_open(){
  timeout 1 bash -c ">/dev/tcp/127.0.0.1/$1" >/dev/null 2>&1
}

need_install=0
for cmd in Xvfb openbox x11vnc websockify openssl; do
  command -v "$cmd" >/dev/null 2>&1 || need_install=1
done

if [[ "$need_install" == "1" ]]; then
  echo "AGENT LAB HOST: installazione desktop/noVNC condiviso (una tantum)..."
  sudo apt-get update -y
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    xvfb openbox x11vnc novnc websockify dbus-x11 x11-utils openssl
fi

if [[ ! -f "$VNC_PASSWORD_FILE" || ! -f "$VNC_PASSWORD_TEXT" ]]; then
  echo "AGENT LAB HOST: genero password VNC locale..."
  VNC_PASSWORD="$(openssl rand -hex 4)"
  umask 077
  printf '%s\n' "$VNC_PASSWORD" > "$VNC_PASSWORD_TEXT"
  x11vnc -storepasswd "$VNC_PASSWORD" "$VNC_PASSWORD_FILE" >/dev/null
  chmod 600 "$VNC_PASSWORD_TEXT" "$VNC_PASSWORD_FILE"
fi

if [[ ! -S "/tmp/.X11-unix/X${DISPLAY_NUM}" ]]; then
  echo "AGENT LAB HOST: avvio Xvfb ${DISPLAY_VALUE}..."
  nohup Xvfb "$DISPLAY_VALUE" -screen 0 1440x900x24 -ac -nolisten tcp \
    >"$ROOT/xvfb.log" 2>&1 &
  echo $! >"$ROOT/xvfb.pid"
  for _ in $(seq 1 50); do
    [[ -S "/tmp/.X11-unix/X${DISPLAY_NUM}" ]] && break
    sleep 0.2
  done
fi

if [[ ! -S "/tmp/.X11-unix/X${DISPLAY_NUM}" ]]; then
  echo "ERROR: impossibile avviare Xvfb ${DISPLAY_VALUE}"
  tail -n 40 "$ROOT/xvfb.log" 2>/dev/null || true
  exit 1
fi

export DISPLAY="$DISPLAY_VALUE"

if ! pgrep -af "openbox.*${DISPLAY_VALUE}|openbox" >/dev/null 2>&1; then
  echo "AGENT LAB HOST: avvio openbox..."
  nohup dbus-launch --exit-with-session openbox-session \
    >"$ROOT/openbox.log" 2>&1 &
  echo $! >"$ROOT/openbox.pid"
fi

# Recycle legacy passwordless x11vnc if present.
if pgrep -af "x11vnc.*-rfbport ${VNC_PORT}.*-nopw|x11vnc.*-nopw.*-rfbport ${VNC_PORT}" >/dev/null 2>&1; then
  pkill -f "x11vnc.*-rfbport ${VNC_PORT}" 2>/dev/null || true
  sleep 0.5
fi

if ! port_open "$VNC_PORT"; then
  pkill -f "x11vnc.*-rfbport ${VNC_PORT}" 2>/dev/null || true
  echo "AGENT LAB HOST: avvio/ripristino x11vnc protetto su localhost:${VNC_PORT}..."
  nohup x11vnc -display "$DISPLAY_VALUE" -forever -shared \
    -rfbauth "$VNC_PASSWORD_FILE" \
    -listen 127.0.0.1 -rfbport "$VNC_PORT" -noxdamage \
    >"$ROOT/x11vnc.log" 2>&1 &
  echo $! >"$ROOT/x11vnc.pid"
  for _ in $(seq 1 50); do
    port_open "$VNC_PORT" && break
    sleep 0.2
  done
fi

if ! port_open "$VNC_PORT"; then
  echo "ERROR: x11vnc non raggiungibile su localhost:${VNC_PORT}"
  tail -n 40 "$ROOT/x11vnc.log" 2>/dev/null || true
  exit 1
fi

NOVNC_WEB="/usr/share/novnc"

if ! port_open "$WEB_PORT" || ! curl -fsS "http://127.0.0.1:${WEB_PORT}/vnc.html" >/dev/null 2>&1; then
  pkill -f "websockify.*${WEB_PORT}.*${VNC_PORT}" 2>/dev/null || true
  echo "AGENT LAB HOST: avvio/ripristino noVNC/websockify su porta ${WEB_PORT}..."
  nohup websockify -v --web="$NOVNC_WEB" "0.0.0.0:${WEB_PORT}" "127.0.0.1:${VNC_PORT}" \
    >"$ROOT/websockify.log" 2>&1 &
  echo $! >"$ROOT/websockify.pid"
fi

for _ in $(seq 1 50); do
  if port_open "$WEB_PORT" && curl -fsS "http://127.0.0.1:${WEB_PORT}/vnc.html" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

if ! port_open "$WEB_PORT" || ! curl -fsS "http://127.0.0.1:${WEB_PORT}/vnc.html" >/dev/null 2>&1; then
  echo "ERROR: noVNC non raggiungibile sulla porta ${WEB_PORT}"
  tail -n 40 "$ROOT/websockify.log" 2>/dev/null || true
  exit 1
fi

CACHE_BUST="$(date +%s)"
if [[ -n "${CODESPACE_NAME:-}" && -n "${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-}" ]]; then
  URL="https://${CODESPACE_NAME}-${WEB_PORT}.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}/vnc.html?autoconnect=true&resize=scale&path=websockify&logging=debug&_=${CACHE_BUST}"
else
  URL="http://127.0.0.1:${WEB_PORT}/vnc.html?autoconnect=true&resize=scale&path=websockify&logging=debug&_=${CACHE_BUST}"
fi

cat <<EOF
AGENT LAB DESKTOP READY
DISPLAY=${DISPLAY_VALUE}
VNC_PORT=${VNC_PORT}
WEB_PORT=${WEB_PORT}
VNC_HEALTH=OK
NOVNC_HEALTH=OK
VNC_AUTH=PASSWORD
VNC_PASSWORD_FILE=${VNC_PASSWORD_TEXT}
Open this browser URL:
${URL}
EOF
