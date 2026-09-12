import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const CDP=process.env.GROK_LAB_CDP_URL||'http://127.0.0.1:9226';
const OUT=path.resolve('certifications');
const TEST='HIVE-GROK-STRESS-0002';
const nonce=crypto.randomBytes(4).toString('hex').toUpperCase();
const MASTER={salt:7919,coeff:[17,29,43]};
const A=[311,7,19,23,5],B=[41,53,67,71,73],C=[79,83,89,97,101];
const sums=[A,B,C].map(x=>x.reduce((a,b)=>a+b,0));
const terms=MASTER.coeff.map((c,i)=>c*sums[i]);
const expected=MASTER.salt+terms.reduce((a,b)=>a+b,0);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const log=(...x)=>console.log(new Date().toISOString(),...x);

async function visible(page,selectors){
  for(const sel of selectors){
    const all=page.locator(sel); const n=await all.count().catch(()=>0);
    for(let i=n-1;i>=0;i--){const x=all.nth(i);if(await x.isVisible().catch(()=>false))return x;}
  }
  return null;
}

async function composer(page){
  return visible(page,[
    '[data-testid="grokInput"]','textarea[data-testid="grok-compose-input"]',
    'textarea[aria-label="Ask Grok anything"]','textarea[placeholder*="Grok" i]',
    'textarea[placeholder*="Ask" i]','div[contenteditable="true"][data-lexical-editor="true"]',
    'div[contenteditable="true"]','textarea'
  ]);
}

async function textOf(c){
  const tag=await c.evaluate(el=>el.tagName.toLowerCase()).catch(()=> 'div');
  return ['textarea','input'].includes(tag)?c.inputValue().catch(()=> ''):c.innerText().catch(()=> '');
}

async function body(page){return page.locator('body').innerText().catch(()=> '');}
const count=(txt,tok)=>tok?txt.split(tok).length-1:0;

async function send(page,text){
  const c=await composer(page); if(!c)throw new Error('GROK_COMPOSER_NOT_FOUND');
  await c.click();
  const tag=await c.evaluate(el=>el.tagName.toLowerCase()).catch(()=> 'div');
  if(['textarea','input'].includes(tag)) await c.fill(text);
  else await c.fill(text).catch(async()=>{
    await c.evaluate((el,t)=>{el.focus();el.textContent=t;el.dispatchEvent(new InputEvent('input',{bubbles:true,composed:true,inputType:'insertText',data:t}));},text);
  });
  if((await textOf(c)).trim().length<10)throw new Error('GROK_TEXT_NOT_INSERTED');

  const btn=await visible(page,[
    'button[aria-label="Submit"]','button[aria-label="Send message"]',
    'button[aria-label*="Send" i]','button[aria-label*="Submit" i]',
    'button[data-testid="send-button"]','button[data-testid*="submit" i]',
    'button[data-testid*="send" i]','button[type="submit"]'
  ]);
  if(btn){await btn.click();log('SUBMIT button');}
  else {await c.press('Enter');log('SUBMIT enter');}

  const started=Date.now();
  while(Date.now()-started<8000){if((await textOf(c).catch(()=> '')).trim().length<5)return;await sleep(250);}
  throw new Error('GROK_PROMPT_NOT_SUBMITTED');
}

async function diagnostic(page,label){
  fs.mkdirSync(OUT,{recursive:true});
  const base=path.join(OUT,`${TEST}-${nonce}-${label}`);
  const c=await composer(page).catch(()=>null);
  fs.writeFileSync(`${base}.txt`,`URL=${page.url()}\nCOMPOSER=${c?await textOf(c).catch(()=> ''):''}\n\n${(await body(page)).slice(-20000)}`);
  await page.screenshot({path:`${base}.png`}).catch(()=>{});
  console.error(`DIAGNOSTIC=${base}.txt`);
}

async function stage(page,label,prompt,echo){
  const before=count(await body(page),echo);log('SEND',label);await send(page,prompt);
  const start=Date.now();
  while(Date.now()-start<90000){if(count(await body(page),echo)>=before+2){log('PASS',label,'exact-body-echo');return;}await sleep(800);}
  await diagnostic(page,label);throw new Error(`TIMEOUT_${label}`);
}

async function main(){
  fs.mkdirSync(OUT,{recursive:true});
  log('START',TEST,`nonce=${nonce}`,`expected=${expected}`);
  const browser=await chromium.connectOverCDP(CDP);
  const context=browser.contexts()[0]||await browser.newContext();
  const page=await context.newPage();
  await page.goto('https://grok.com/',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(2500);
  if(!await composer(page))throw new Error('GROK_NOT_AUTHENTICATED_OR_COMPOSER_NOT_FOUND');

  const em=`ACK_MASTER:${nonce}:${MASTER.salt}:${MASTER.coeff.join(',')}`;
  await stage(page,'MASTER',[`${TEST} / ${nonce}`,`SALT=${MASTER.salt}`,`COEFF=${MASTER.coeff.join(',')}`,`Rispondi ESATTAMENTE: ${em}`].join('\n'),em);
  for(const [name,data] of [['A',A],['B',B],['C',C]]){
    const e=`ACK_${name}:${nonce}:${data.join(',')}`;
    await stage(page,`SHARD_${name}`,[`${TEST} / ${nonce}`,`SHARD_${name}=${data.join(',')}`,`Rispondi ESATTAMENTE: ${e}`].join('\n'),e);
  }

  const finalPrefix=`GROK_CERT_RESULT:${nonce}:`;
  log('SEND FINAL');
  await send(page,[`${TEST} / ${nonce}`,'Usa i dati memorizzati.',`Rispondi ESATTAMENTE: ${finalPrefix}<SALT>:<C1>,<C2>,<C3>:<S1>,<S2>,<S3>:<T1>,<T2>,<T3>:<CHECKSUM>`].join('\n'));
  const re=new RegExp(`GROK_CERT_RESULT:${nonce}:(\\d+):(\\d+),(\\d+),(\\d+):(\\d+),(\\d+),(\\d+):(\\d+),(\\d+),(\\d+):(\\d+)`);
  let m=null; const start=Date.now();
  while(Date.now()-start<120000){m=re.exec(await body(page));if(m)break;await sleep(800);}
  if(!m){await diagnostic(page,'FINAL');throw new Error('TIMEOUT_FINAL');}
  const nums=m.slice(1).map(Number);
  const exp=[MASTER.salt,...MASTER.coeff,...sums,...terms,expected];
  const passed=JSON.stringify(nums)===JSON.stringify(exp);
  const file=path.join(OUT,`${TEST}-${nonce}.json`);
  fs.writeFileSync(file,JSON.stringify({test_id:TEST,nonce,expected:exp,actual:nums,certified:passed},null,2));
  console.log(`GROK_CERTIFIED=${passed}`);console.log(`TEST_ID=${TEST}`);console.log(`NONCE=${nonce}`);
  console.log(`EXPECTED_CHECKSUM=${expected}`);console.log(`ACTUAL_CHECKSUM=${nums[nums.length-1]}`);console.log(`CERTIFICATE=${file}`);
  if(!passed)process.exitCode=2;
  await page.close().catch(()=>{});await browser.close().catch(()=>{});
}
main().catch(e=>{console.error('GROK_CERTIFIED=false');console.error(`ERROR=${e.message}`);process.exit(1);});
