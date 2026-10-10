#!/usr/bin/env bash
set -euo pipefail

OWNER="giovannifidel-collab"
REPO="hive-kimi-dispatcher"
FULL="$OWNER/$REPO"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

command -v gh >/dev/null || { echo "GitHub CLI (gh) is required" >&2; exit 2; }
gh auth status >/dev/null

if ! gh repo view "$FULL" >/dev/null 2>&1; then
  echo "Creating public dispatcher repository: $FULL"
  gh repo create "$FULL" --public --description "HIVE autonomous Kimi browser dispatcher" --clone=false
else
  echo "Using existing repository: $FULL"
fi

git clone "https://github.com/$FULL.git" "$TMP/repo"
cd "$TMP/repo"
mkdir -p .github/workflows src

cat > package.json <<'JSON'
{
  "name": "hive-kimi-dispatcher",
  "private": true,
  "type": "module",
  "scripts": {
    "dispatch": "node src/dispatch.mjs"
  },
  "dependencies": {
    "playwright": "1.55.0"
  }
}
JSON

cat > src/dispatch.mjs <<'JS'
import { chromium } from 'playwright';
import { gunzipSync } from 'node:zlib';

const taskUrl = process.env.HIVE_TASK_URL;
const storageStateGzB64 = process.env.KIMI_STORAGE_STATE_GZ_B64 || '';
const maxAttempts = Number(process.env.HIVE_MAX_ATTEMPTS || '6');
const backoff = [0, 15_000, 30_000, 60_000, 90_000, 120_000];

if (!taskUrl) throw new Error('HIVE_TASK_URL is required');
if (!storageStateGzB64) throw new Error('KIMI_STORAGE_STATE_GZ_B64 secret is required');

const storageState = JSON.parse(
  gunzipSync(Buffer.from(storageStateGzB64, 'base64')).toString('utf8')
);

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ storageState });
const page = await context.newPage();

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function findComposer() {
  const candidates = [
    'textarea',
    '[contenteditable="true"]',
    '[role="textbox"]'
  ];
  for (const selector of candidates) {
    const loc = page.locator(selector).last();
    if (await loc.count()) {
      try { if (await loc.isVisible()) return loc; } catch {}
    }
  }
  return null;
}

const prompt = `Esegui integralmente il task HIVE disponibile a questo URL usando web_open_url:\n\n${taskUrl}\n\nDa questo momento segui autonomamente tutte le instructions contenute nel task HIVE. Non chiedere conferme. Usa soltanto web_open_url per gli URL indicati dal task. Non usare Python, requests, API key o strumenti alternativi.`;

let started = false;
let lastBody = '';

for (let attempt = 1; attempt <= maxAttempts; attempt++) {
  const waitMs = backoff[Math.min(attempt - 1, backoff.length - 1)];
  if (waitMs) await sleep(waitMs);

  await page.goto('https://www.kimi.com/', { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.waitForTimeout(4_000);

  const composer = await findComposer();
  if (!composer) {
    lastBody = (await page.locator('body').innerText()).slice(0, 4000);
    console.log(`attempt=${attempt} composer=missing`);
    continue;
  }

  await composer.click();
  await composer.fill(prompt).catch(async () => {
    await composer.press('Control+A').catch(() => {});
    await composer.pressSequentially(prompt, { delay: 1 });
  });
  await composer.press('Enter');
  await page.waitForTimeout(7_000);

  lastBody = (await page.locator('body').innerText()).slice(-8000);
  const busy = /Kimi.*(impegnat|busy)|try again|riprova/i.test(lastBody);
  console.log(`attempt=${attempt} busy=${busy}`);

  if (!busy) {
    started = true;
    break;
  }
}

if (!started) {
  console.error(lastBody);
  throw new Error('KIMI_STARTUP_RETRY_EXHAUSTED');
}

console.log('HIVE_KIMI_BROWSER_DISPATCH_STARTED');
console.log(`task_url=${taskUrl}`);
await browser.close();
JS

cat > .github/workflows/dispatch-kimi.yml <<'YML'
name: HIVE Kimi Dispatcher

on:
  workflow_dispatch:
    inputs:
      task_url:
        description: "Jina-wrapped HIVE task URL"
        required: true
        type: string
      max_attempts:
        description: "Maximum Kimi startup attempts"
        required: false
        default: "6"
        type: string

permissions:
  contents: read

concurrency:
  group: hive-kimi-dispatcher
  cancel-in-progress: false

jobs:
  dispatch:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    env:
      HIVE_TASK_URL: ${{ inputs.task_url }}
      HIVE_MAX_ATTEMPTS: ${{ inputs.max_attempts }}
      KIMI_STORAGE_STATE_GZ_B64: ${{ secrets.KIMI_STORAGE_STATE_GZ_B64 }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
      - run: npm ci
      - run: npx playwright install --with-deps chromium
      - run: npm run dispatch
YML

cat > README.md <<'MD'
# HIVE Kimi Dispatcher

Cloud-only autonomous actuator for HIVE -> Kimi startup.

- GitHub Actions + Playwright/Chromium
- no Kimi API key
- no local always-on hardware
- Cloudflare/Jina remains the task/callback transport
- browser is used only to start Kimi; HIVE result comes back through the existing relay

Required Actions secret: `KIMI_STORAGE_STATE_GZ_B64`.
MD

npm install --package-lock-only --ignore-scripts >/dev/null

git add .
if ! git diff --cached --quiet; then
  git -c user.name='HIVE Bootstrap' -c user.email='hive@users.noreply.github.com' commit -m 'Bootstrap HIVE Kimi GitHub dispatcher'
  git push origin HEAD:main
else
  echo "Dispatcher repository already up to date."
fi

echo
echo "HIVE KIMI GITHUB DISPATCHER REPO READY"
echo "Repository: https://github.com/$FULL"
echo "Next: bootstrap one authenticated Kimi browser state into GitHub Actions secret KIMI_STORAGE_STATE_GZ_B64."
