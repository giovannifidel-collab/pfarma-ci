import { chromium } from 'playwright';
import { readFileSync, writeFileSync, mkdtempSync, mkdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';

const triggerPath = process.env.HIVE_TRIGGER_FILE || 'hive-kimi-dispatcher/trigger.json';
const trigger = JSON.parse(readFileSync(triggerPath, 'utf8'));
const taskUrl = trigger.task_url || '';
const resultUrl = trigger.result_url || '';
const taskId = trigger.task_id || 'unknown';
const maxAttempts = Number(trigger.max_attempts || 6);
const inlinePrompt = String(trigger.inline_prompt || '');
const inlineExpected = String(trigger.inline_expected || '');
const inlineMode = Boolean(inlinePrompt && inlineExpected);
const sessionEndpoint = 'https://hive-kimi-relay.project-giovanni.workers.dev/dispatcher/session';
const oidcAudience = 'hive-kimi-dispatcher';
const kimiTargets = ['https://kimi.ai/', 'https://www.kimi.com/en'];

if (!inlineMode && !taskUrl) throw new Error('trigger.task_url is required');
if (!inlineMode && !resultUrl) throw new Error('trigger.result_url is required');

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const backoff = [0, 15_000, 30_000, 60_000, 90_000, 120_000];

async function getGithubOidcToken() {
  const requestUrl = process.env.ACTIONS_ID_TOKEN_REQUEST_URL || '';
  const requestToken = process.env.ACTIONS_ID_TOKEN_REQUEST_TOKEN || '';
  if (!requestUrl || !requestToken) throw new Error('GITHUB_OIDC_ENV_MISSING');
  const separator = requestUrl.includes('?') ? '&' : '?';
  const response = await fetch(`${requestUrl}${separator}audience=${encodeURIComponent(oidcAudience)}`, {
    headers: { Authorization: `bearer ${requestToken}` },
  });
  if (!response.ok) throw new Error(`GITHUB_OIDC_TOKEN_FAILED_${response.status}`);
  const payload = await response.json();
  if (!payload?.value) throw new Error('GITHUB_OIDC_TOKEN_EMPTY');
  return payload.value;
}

async function leaseKimiProfile() {
  const oidcToken = await getGithubOidcToken();
  const response = await fetch(sessionEndpoint, {
    headers: { Authorization: `Bearer ${oidcToken}`, 'cache-control': 'no-cache' },
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`HIVE_PROFILE_LEASE_FAILED_${response.status}:${text.slice(0, 500)}`);
  const payload = JSON.parse(text);
  if (!payload?.ok || !payload?.session) throw new Error('HIVE_PROFILE_LEASE_EMPTY');
  if (payload.format !== 'tar-gzip-base64-chromium-user-data-dir') {
    throw new Error(`HIVE_PROFILE_FORMAT_UNEXPECTED:${payload.format || 'missing'}`);
  }
  return Buffer.from(payload.session, 'base64');
}

const tempRoot = mkdtempSync(join(tmpdir(), 'hive-kimi-profile-'));
const archivePath = join(tempRoot, 'profile.tar.gz');
const profileDir = join(tempRoot, 'profile');
mkdirSync(profileDir, { recursive: true });

const profileArchive = await leaseKimiProfile();
writeFileSync(archivePath, profileArchive);
console.log(`HIVE_KIMI_FULL_PROFILE_LEASED_VIA_GITHUB_OIDC bytes=${profileArchive.length}`);
execFileSync('tar', ['-xzf', archivePath, '-C', profileDir], { stdio: 'inherit' });
console.log('HIVE_KIMI_FULL_PROFILE_RESTORED');

const context = await chromium.launchPersistentContext(profileDir, {
  headless: true,
  viewport: { width: 1440, height: 1000 },
  args: ['--password-store=basic', '--no-sandbox', '--disable-dev-shm-usage'],
});
const pages = context.pages();
const page = pages[0] || await context.newPage();

async function findComposer() {
  for (const selector of ['textarea:visible', '[contenteditable="true"]:visible', '[role="textbox"]:visible']) {
    const loc = page.locator(selector).last();
    if (await loc.count()) return loc;
  }
  return null;
}

async function bodyText() {
  try { return await page.locator('body').innerText(); } catch { return ''; }
}

function hasLoginGate(text) {
  return /微信扫码登录|手机号登录|登录以同步历史|Log in to sync chat history|Sign in to sync chat history|Google login users|谷歌登录用户/i.test(text || '');
}

const prompt = inlineMode
  ? inlinePrompt
  : `Esegui integralmente il task HIVE disponibile a questo URL usando web_open_url:\n\n${taskUrl}\n\nDa questo momento segui autonomamente tutte le instructions contenute nel task HIVE. Non chiedermi conferme e non richiedere interventi tra uno step e il successivo. Usa soltanto web_open_url per gli URL indicati dal task. Non usare Python, requests, API key o strumenti alternativi. Alla fine esegui il callback HIVE previsto dal task.`;

let started = false;
let lastText = '';
let certified = false;
let authGateSeen = false;

try {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const delay = backoff[Math.min(attempt - 1, backoff.length - 1)];
    if (delay) await sleep(delay);
    const target = kimiTargets[(attempt - 1) % kimiTargets.length];
    await page.goto(target, { waitUntil: 'domcontentloaded', timeout: 60_000 });
    await page.waitForTimeout(6_000);

    lastText = await bodyText();
    if (hasLoginGate(lastText)) {
      authGateSeen = true;
      console.log(`HIVE_DISPATCH attempt=${attempt} target=${target} auth_gate=preexisting`);
      await page.screenshot({ path: `hive-kimi-dispatcher-auth-${attempt}.png`, fullPage: true }).catch(() => {});
      continue;
    }

    const composer = await findComposer();
    if (!composer) {
      console.log(`HIVE_DISPATCH attempt=${attempt} target=${target} composer=missing url=${page.url()}`);
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
    await page.waitForTimeout(12_000);

    lastText = (await bodyText()).slice(-16000);
    if (hasLoginGate(lastText)) {
      authGateSeen = true;
      console.log(`HIVE_DISPATCH attempt=${attempt} target=${target} auth_gate=after_submit`);
      await page.screenshot({ path: `hive-kimi-dispatcher-auth-${attempt}.png`, fullPage: true }).catch(() => {});
      continue;
    }

    const busy = /Kimi.{0,40}(impegnat|busy)|server.{0,20}busy|try again|riprova|系统繁忙|稍后重试/i.test(lastText);
    console.log(`HIVE_DISPATCH attempt=${attempt} target=${target} busy=${busy}`);
    if (!busy) {
      started = true;
      console.log(`HIVE_KIMI_BROWSER_DISPATCH_STARTED task_id=${taskId} attempt=${attempt} target=${target}`);
      break;
    }
  }

  if (!started) {
    await page.screenshot({ path: 'hive-kimi-dispatcher-failure.png', fullPage: true }).catch(() => {});
    throw new Error(authGateSeen ? 'KIMI_AUTH_FULL_PROFILE_NOT_RESTORED' : 'KIMI_STARTUP_RETRY_EXHAUSTED');
  }

  if (inlineMode) {
    const deadline = Date.now() + 3 * 60_000;
    while (Date.now() < deadline) {
      const text = await bodyText();
      if (text.includes(inlineExpected)) {
        certified = true;
        console.log(`HIVE_KIMI_FRESH_EXECUTION_CERTIFIED task_id=${taskId} expected=${inlineExpected}`);
        break;
      }
      await sleep(5_000);
    }
    if (!certified) {
      await page.screenshot({ path: 'hive-kimi-dispatcher-timeout.png', fullPage: true }).catch(() => {});
      throw new Error('HIVE_FRESH_EXECUTION_TIMEOUT');
    }
  } else {
    const deadline = Date.now() + 8 * 60_000;
    while (Date.now() < deadline) {
      try {
        const response = await fetch(resultUrl, { headers: { 'cache-control': 'no-cache' } });
        const data = await response.json();
        console.log(`HIVE_RESULT_POLL task_id=${taskId} certified=${data?.certified === true}`);
        if (data?.certified === true) {
          certified = true;
          console.log('HIVE_KIMI_AUTONOMOUS_ROUNDTRIP_CERTIFIED');
          console.log(JSON.stringify(data));
          break;
        }
      } catch (error) {
        console.log(`HIVE_RESULT_POLL_ERROR ${error instanceof Error ? error.message : String(error)}`);
      }
      await sleep(10_000);
    }
    if (!certified) {
      await page.screenshot({ path: 'hive-kimi-dispatcher-timeout.png', fullPage: true }).catch(() => {});
      throw new Error('HIVE_RESULT_CERTIFICATION_TIMEOUT');
    }
  }
} finally {
  await context.close().catch(() => {});
  rmSync(tempRoot, { recursive: true, force: true });
}
