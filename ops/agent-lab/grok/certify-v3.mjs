import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const CDP=process.env.GROK_LAB_CDP_URL||'http://127.0.0.1:9226';
const OUT=path.resolve('certifications');
const TEST='HIVE-GROK-STRESS-0003';
const nonce=crypto.randomBytes(4).toString('hex').toUpperCase();
const MASTER={salt:7919,coeff:[17,29,43]};
const SHARDS={A:[311,7,19,23,5],B:[41,53,67,71,73],C:[79,83,89,97,101]};
const sums={A:365,B:305,C:449};
const expected=42276;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const log=(...x)=>console.log(new Date().toISOString(),...x);

async function visible(page,selectors){
  for(const sel of selectors){
    const all=page.locator(sel); const n=await all.count().catch(()=>0);
    for(let i=n-1;i>=0;i--){ const x=all.nth(i); if(await x.isVisible().catch(()=>false)) return x; }
  }
  return null;
}

async function composer(page){
  return visible(page,[
    '[data-testid="grokInput"]','textarea[data-testid="grok-compose-input"]',
    'textarea[aria-label*="Ask" i]','textarea[placeholder*="Ask" i]',
    'div[contenteditable="true"][data-lexical-editor="true"]','div[contenteditable="true"]','textarea'
  ]);
}

async function body(page){ return page.locator('body').innerText().catch(()=> ''); }
const count=(txt,tok)=>tok?txt.split(tok).length-1:0;

async function textOf(c){
  const tag=await c.evaluate(el=>el.tagName.toLowerCase()).catch(()=> 'div');
  return ['textarea','input'].includes(tag)?c.inputValue().catch(()=> ''):c.innerText().catch(()=> '');
}

async function send(page,text){
  const c=await composer(page); if(!c) throw new Error('GROK_COMPOSER_NOT_FOUND');
  await c.click();
  const tag=await c.evaluate(el=>el.tagName.toLowerCase()).catch(()=> 'div');
  if(['textarea','input'].includes(tag)) await c.fill(text);
  else await c.fill(text).catch(async()=>c.evaluate((el,t)=>{el.focus();el.textContent=t;el.dispatchEvent(new InputEvent('input',{bubbles:true,composed:true,inputType:'insertText',data:t}));},text));
  const btn=await visible(page,['button[aria-label="Submit"]','button[aria-label*="Send" i]','button[aria-label*="Submit" i]','button[data-testid*="send" i]','button[data-testid*="submit" i]','button[type="submit"]']);
  if(btn){ await btn.click(); log('SUBMIT button'); } else { await c.press('Enter'); log('SUBMIT enter'); }
  const start=Date.now();
  while(Date.now()-start<8000){ if((await textOf(c).catch(()=> '')).trim().length<5) return; await sleep(250); }
  throw new Error('GROK_PROMPT_NOT_SUBMITTED');
}

async function stage(page,label,prompt,echo){
  const before=count(await body(page),echo); log('SEND',label); await send(page,prompt);
  const start=Date.now();
  while(Date.now()-start<90000){ if(count(await body(page),echo)>=before+2){ log('PASS',label,'exact-body-echo'); return; } await sleep(800); }
  throw new Error(`TIMEOUT_${label}`);
}

async function findReadyPage(context){
  for(const p of context.pages()){
    if(p.url().includes('grok.com') && await composer(p).catch(()=>null)) return p;
  }
  const p=await context.newPage();
  await p.goto('https://grok.com/',{waitUntil:'domcontentloaded',timeout:60000});
  const start=Date.now();
  while(Date.now()-start<30000){ if(await composer(p).catch(()=>null)) return p; await sleep(1000); }
  throw new Error(`GROK_NOT_AUTHENTICATED_OR_COMPOSER_NOT_FOUND url=${p.url()}`);
}

async function main(){
  fs.mkdirSync(OUT,{recursive:true});
  log('START',TEST,`nonce=${nonce}`,`expected=${expected}`);
  const browser=await chromium.connectOverCDP(CDP);
  const context=browser.contexts()[0]||await browser.newContext();
  const page=await findReadyPage(context);

  const master=`ACK_MASTER:${nonce}:${MASTER.salt}:${MASTER.coeff.join(',')}`;
  await stage(page,'MASTER',[`${TEST} / ${nonce}`,`SALT=${MASTER.salt}`,`COEFF=${MASTER.coeff.join(',')}`,`Rispondi ESATTAMENTE: ${master}`].join('\n'),master);

  for(const name of ['A','B','C']){
    const data=SHARDS[name];
    const echo=`ACK_${name}:${nonce}:${data.join(',')}`;
    await stage(page,`SHARD_${name}`,[`${TEST} / ${nonce}`,`SHARD_${name}=${data.join(',')}`,`Rispondi ESATTAMENTE: ${echo}`].join('\n'),echo);
  }

  const token=`GROK_CERT_RESULT:${nonce}:`;
  log('SEND FINAL');
  await send(page,[`${TEST} / ${nonce}`,'Usa SOLO il MASTER e i tre SHARD memorizzati.','Calcola SUM_A, SUM_B e SUM_C; poi CHECKSUM = SALT + COEFF_A*SUM_A + COEFF_B*SUM_B + COEFF_C*SUM_C.','Non aggiungere spiegazioni.',`Rispondi ESATTAMENTE: ${token}<CHECKSUM>`].join('\n'));

  const re=new RegExp(`GROK_CERT_RESULT:${nonce}:(\\d+)`);
  let actual=null; const start=Date.now();
  while(Date.now()-start<120000){ const m=re.exec(await body(page)); if(m){ actual=Number(m[1]); break; } await sleep(800); }
  if(actual===null) throw new Error('TIMEOUT_FINAL');

  const passed=actual===expected;
  const file=path.join(OUT,`${TEST}-${nonce}.json`);
  fs.writeFileSync(file,JSON.stringify({test_id:TEST,nonce,master_verified:true,shards_verified:true,expected_sums:sums,expected_checksum:expected,actual_checksum:actual,certified:passed},null,2));
  console.log(`GROK_CERTIFIED=${passed}`);
  console.log(`TEST_ID=${TEST}`);
  console.log(`NONCE=${nonce}`);
  console.log(`EXPECTED_CHECKSUM=${expected}`);
  console.log(`ACTUAL_CHECKSUM=${actual}`);
  console.log(`CERTIFICATE=${file}`);
  if(!passed) process.exitCode=2;
  await browser.close().catch(()=>{});
}

main().catch(e=>{ console.error('GROK_CERTIFIED=false'); console.error(`ERROR=${e.message}`); process.exit(1); });
