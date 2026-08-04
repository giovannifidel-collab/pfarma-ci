#!/usr/bin/env bash
set -euo pipefail

: "${RUNNER_TOKEN:?Set a short-lived GitHub Actions runner registration token}"
: "${RUNNER_URL:=https://github.com/giovannifidel-collab}"
: "${RUNNER_NAME:=razzo-persistent-$(hostname)}"

ROOT="${RAZZO_RUNNER_ROOT:-/opt/razzo}"
sudo mkdir -p "$ROOT/runner" "$ROOT/cache" "$ROOT/work"
sudo chown -R "$USER":"$USER" "$ROOT"
cd "$ROOT/runner"

if [[ ! -x config.sh ]]; then
  version="${RUNNER_VERSION:-2.336.0}"
  curl -fsSLo actions-runner.tar.gz "https://github.com/actions/runner/releases/download/v${version}/actions-runner-linux-x64-${version}.tar.gz"
  tar xzf actions-runner.tar.gz
fi

./config.sh --unattended --replace --url "$RUNNER_URL" --token "$RUNNER_TOKEN" \
  --name "$RUNNER_NAME" --labels "razzo-persistent,linux,x64" --work "$ROOT/work"

sudo ./svc.sh install "$USER"
sudo ./svc.sh start

echo "RAZZO persistent runner installed: $RUNNER_NAME"
