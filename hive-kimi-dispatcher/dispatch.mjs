import { chromium } from 'playwright';
import { gunzipSync } from 'node:zlib';
import { readFileSync } from 'node:fs';

const triggerPath = process.env.HIVE_TRIGGER_FILE || 'hive-kimi-dispatcher/trigger.json';
const trigger = JSON.parse(readFileSync(triggerPath, 'utf8'));
const taskUrl = trigger.task_url;
const resultUrl = trigger.result_url;
const taskId = trigger.task_id || 'unknown';
const maxAttempts = Number(trigger.max_attempts || 6);
const secret = process.env.KIMI_STORAGE_STATE_GZ_B64 || '';

if (!taskUrl) throw new Error('trigger.task_url is required');
if (!resultUrl) throw new Error('trigger.result_url is required');
if (!secret) throw new Error('KIMI_STORAGE_STATE_GZ_B64 secret is required');

const storageState = JSON.parse(gunzipSync(Buffer.from(secret, 'base64')).toString('utf8'));
const backoff = [0, 15_000, 30_000, 60_000, 90_000, 120_000];
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ storageState, viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();

async function findComposer() {
  const selectors = [
    'textarea:visible',
    '[contenteditable="true"]:visible',
    '[role="textbox"]:visible'
  ];
  for (const selector of selectors) {
    const loc = page.locator(selector).last();
    if (await loc.count()) return loc;
  }
  return null;
}

async function bodyText() {
  try { return await page.locator('body').innerText(); } catch { return ''; }
}

const prompt = `Esegui integralmente il task HIVE disponibile a questo URL usando web_open_url:\n\n${taskUrl}\n\nDa questo momento segui autonomamente tutte le instructions contenute nel task HIVE. Non chiedermi conferme e non richiedere interventi tra uno step e il successivo. Usa soltanto web_open_url per gli URL indicati dal task. Non usare Python, requests, API key o strumenti alternativi. Alla fine esegui il callback HIVE previsto dal task.`;

let started = false;
let lastText = '';

try {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const delay = backoff[Math.min(attempt - 1, backoff.length - 1)];
    if (delay) await sleep(delay);

    await page.goto('https://www.kimi.com/', { waitUntil: 'domcontentloaded', timeout: 60_000 });
    await page.waitForTimeout(5_000);

    const composer = await findComposer();
    if (!composer) {
      lastText = (await bodyText()).slice(0, 5000);
      console.log(`HIVE_DISPATCH attempt=${attempt} composer=missing url=${page.url()}`);
      continue;
    }

    await composer.click();
    try {
      await composer.fill(prompt);
    } catch {
      await composer.press('Control+A').catch(() => {});
      await composer.pressSequentially(prompt, { delay: 1 });
    }
    await composer.press('Enter');
    await page.waitForTimeout(10_000);

    lastText = (await bodyText()).slice(-12000);
    const busy = /Kimi.{0,40}(impegnat|busy)|server.{0,20}busy|try again|riprova|系统繁忙|稍后重试/i.test(lastText);
    console.log(`HIVE_DISPATCH attempt=${attempt} busy=${busy}`);

    if (!busy) {
      started = true;
      console.log(`HIVE_KIMI_BROWSER_DISPATCH_STARTED task_id=${taskId} attempt=${attempt}`);
      break;
    }
  }

  if (!started) {
    await page.screenshot({ path: 'hive-kimi-dispatcher-failure.png', fullPage: true }).catch(() => {});
    console.error(lastText);
    throw new Error('KIMI_STARTUP_RETRY_EXHAUSTED');
  }

  const deadline = Date.now() + 8 * 60_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(resultUrl, { headers: { 'cache-control': 'no-cache' } });
      const data = await response.json();
      console.log(`HIVE_RESULT_POLL task_id=${taskId} certified=${data?.certified === true}`);
      if (data?.certified === true) {
        console.log('HIVE_KIMI_AUTONOMOUS_ROUNDTRIP_CERTIFIED');
        console.log(JSON.stringify(data));
        process.exitCode = 0;
        break;
      }
    } catch (error) {
      console.log(`HIVE_RESULT_POLL_ERROR ${error instanceof Error ? error.message : String(error)}`);
    }
    await sleep(10_000);
  }

  if (process.exitCode !== 0) {
    await page.screenshot({ path: 'hive-kimi-dispatcher-timeout.png', fullPage: true }).catch(() => {});
    throw new Error('HIVE_RESULT_CERTIFICATION_TIMEOUT');
  }
} finally {
  await browser.close();
}
