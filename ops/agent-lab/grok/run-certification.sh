#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d node_modules/playwright ]]; then
  echo "GROK LAB: installazione dipendenze..."
  npm install
fi

bash ./start-browser.sh

export GROK_LAB_CDP_URL="${GROK_LAB_CDP_URL:-http://127.0.0.1:9226}"

# Keep at least one non-Grok page alive so closing the last Grok tab does not
# terminate Chromium's persistent browser context before a fresh trial starts.
node --input-type=module <<'JS'
import { chromium } from 'playwright';
const url=process.env.GROK_LAB_CDP_URL||'http://127.0.0.1:9226';
const browser=await chromium.connectOverCDP(url);
const context=browser.contexts()[0]||await browser.newContext();
const keeper=await context.newPage();
await keeper.goto('about:blank');
console.log('GROK KEEPER PAGE READY');
process.exit(0);
JS

node certify-v7.mjs
