import { chromium } from 'playwright';

const CDP=process.env.GROK_LAB_CDP_URL||'http://127.0.0.1:9226';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

async function visible(page,sel){
  const list=page.locator(sel); const n=await list.count().catch(()=>0);
  for(let i=n-1;i>=0;i--){const x=list.nth(i);if(await x.isVisible().catch(()=>false))return x;}
  return null;
}

const browser=await chromium.connectOverCDP(CDP);
const context=browser.contexts()[0];
if(!context) throw new Error('NO_BROWSER_CONTEXT');
const page=context.pages().find(p=>p.url().includes('grok.com'));
if(!page) throw new Error('NO_GROK_PAGE');

console.log('=== GROK MODEL PROBE ===');
console.log(`URL=${page.url()}`);
const modelBtn=await visible(page,'button[aria-label="Model select"]');
if(!modelBtn) throw new Error('MODEL_SELECT_NOT_FOUND');
console.log('MODEL_SELECT_FOUND=true');
await modelBtn.click();
await sleep(800);

const roles=['[role="menuitem"]','[role="option"]','[role="menu"] button','[role="listbox"] button','[data-radix-menu-content] button','[data-radix-popper-content-wrapper] button'];
let items=[];
for(const sel of roles){
  const loc=page.locator(sel); const n=await loc.count().catch(()=>0);
  for(let i=0;i<n;i++){
    const x=loc.nth(i);
    if(!await x.isVisible().catch(()=>false)) continue;
    const text=(await x.innerText().catch(()=> '')).trim();
    const aria=await x.getAttribute('aria-label').catch(()=>null);
    const disabled=!(await x.isEnabled().catch(()=>false));
    if(text||aria) items.push({text,aria,disabled});
  }
  if(items.length) break;
}
if(!items.length){
  const body=(await page.locator('body').innerText().catch(()=> '')).split('\n').map(s=>s.trim()).filter(Boolean);
  const interesting=body.filter(s=>/grok|fast|expert|think|model|mini|auto|beta|super/i.test(s));
  console.log(`MODEL_LINES=${JSON.stringify(interesting.slice(-80),null,2)}`);
}else{
  const uniq=[]; const seen=new Set();
  for(const it of items){const k=JSON.stringify(it);if(!seen.has(k)){seen.add(k);uniq.push(it);}}
  console.log(`MODEL_OPTIONS=${JSON.stringify(uniq,null,2)}`);
}
const bodyText=await page.locator('body').innerText().catch(()=> '');
const limitLines=bodyText.split('\n').map(s=>s.trim()).filter(s=>/limit|upgrade|supergrok|hour|minute|quota|wait/i.test(s));
console.log(`LIMIT_LINES=${JSON.stringify(limitLines.slice(-40),null,2)}`);
process.exit(0);
