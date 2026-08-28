import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const CDP=process.env.CLAUDE_LAB_CDP_URL||'http://127.0.0.1:9224';
const OUT_DIR=process.env.CLAUDE_LAB_CERT_DIR||path.resolve('certifications');
const TEST_ID='HIVE-CLAUDE-STRESS-0001';
const nonce=crypto.randomBytes(4).toString('hex').toUpperCase();
const MASTER={salt:7919,coeff:[17,29,43]};
const SHARDS={A:[311,7,19,23,5],B:[41,53,67,71,73],C:[79,83,89,97,101]};
const EXPECTED=MASTER.salt+MASTER.coeff[0]*SHARDS.A.reduce((a,b)=>a+b,0)+MASTER.coeff[1]*SHARDS.B.reduce((a,b)=>a+b,0)+MASTER.coeff[2]*SHARDS.C.reduce((a,b)=>a+b,0);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const log=(...x)=>console.log(new Date().toISOString(),...x);

async function composer(page){
  for(const sel of ['div[contenteditable="true"][data-placeholder]','div[contenteditable="true"]','textarea[placeholder*="Claude" i]','textarea']){
    const loc=page.locator(sel).filter({visible:true}).last();
    if(await loc.count().catch(()=>0))return loc;
  }
  return null;
}

async function send(page,text){
  const c=await composer(page);
  if(!c)throw new Error('CLAUDE_NOT_AUTHENTICATED_OR_COMPOSER_NOT_FOUND');
  await c.click();
  const tag=await c.evaluate(el=>el.tagName.toLowerCase()).catch(()=> 'div');
  if(tag==='textarea')await c.fill(text);
  else{
    await c.press(process.platform==='darwin'?'Meta+A':'Control+A').catch(()=>{});
    await c.fill(text).catch(async()=>c.evaluate((el,t)=>{el.innerText=t;el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:t}));},text));
  }
  await c.press('Enter');
}

async function waitBodyMatch(page,regex,timeout=90000){
  const started=Date.now();
  while(Date.now()-started<timeout){
    const body=await page.locator('body').innerText().catch(()=> '');
    const m=regex.exec(body);
    if(m)return {match:m,body};
    await sleep(1200);
  }
  throw new Error(`TIMEOUT_WAITING_FOR_${regex}`);
}

async function stage(page,label,prompt,expectedRegex){
  log('SEND',label);
  await send(page,prompt);
  const result=await waitBodyMatch(page,expectedRegex);
  log('PASS',label);
  return result;
}

async function main(){
  fs.mkdirSync(OUT_DIR,{recursive:true});
  const startedAt=new Date().toISOString();
  log(`START ${TEST_ID} nonce=${nonce} expected=${EXPECTED}`);
  const browser=await chromium.connectOverCDP(CDP);
  const context=browser.contexts()[0]||await browser.newContext();
  const page=await context.newPage();
  await page.goto('https://claude.ai/new',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(1500);
  if(!await composer(page))throw new Error('CLAUDE_NOT_AUTHENTICATED_OR_COMPOSER_NOT_FOUND');

  await stage(page,'MASTER',[`${TEST_ID} / ${nonce}`,'Memorizza questo MASTER per un test multi-turn. Non calcolare ancora il risultato finale.',`SALT=${MASTER.salt}`,`COEFF_A=${MASTER.coeff[0]}`,`COEFF_B=${MASTER.coeff[1]}`,`COEFF_C=${MASTER.coeff[2]}`,`Quando hai memorizzato, rispondi ESATTAMENTE: ACK_MASTER:${nonce}`].join('\n'),new RegExp(`ACK_MASTER:${nonce}`));
  await stage(page,'SHARD_A',[`${TEST_ID} / ${nonce}`,`SHARD_A=${SHARDS.A.join(',')}`,`Memorizzalo e rispondi ESATTAMENTE: ACK_A:${nonce}`].join('\n'),new RegExp(`ACK_A:${nonce}`));
  await stage(page,'SHARD_B',[`${TEST_ID} / ${nonce}`,`SHARD_B=${SHARDS.B.join(',')}`,`Memorizzalo e rispondi ESATTAMENTE: ACK_B:${nonce}`].join('\n'),new RegExp(`ACK_B:${nonce}`));
  await stage(page,'SHARD_C',[`${TEST_ID} / ${nonce}`,`SHARD_C=${SHARDS.C.join(',')}`,`Memorizzalo e rispondi ESATTAMENTE: ACK_C:${nonce}`].join('\n'),new RegExp(`ACK_C:${nonce}`));

  log('SEND FINAL');
  await send(page,[`${TEST_ID} / ${nonce}`,'Ora usa SOLO il MASTER e i tre shard ricevuti nei messaggi precedenti.','Calcola: CHECKSUM = SALT + COEFF_A*SUM(SHARD_A) + COEFF_B*SUM(SHARD_B) + COEFF_C*SUM(SHARD_C).','Non aggiungere spiegazioni.',`Rispondi ESATTAMENTE nel formato: CLAUDE_CERT_RESULT:${nonce}:<CHECKSUM>`].join('\n'));
  const final=await waitBodyMatch(page,new RegExp(`CLAUDE_CERT_RESULT:${nonce}:(\\d+)`),120000);
  const actual=Number(final.match[1]);
  const passed=actual===EXPECTED;
  const cert={test_id:TEST_ID,nonce,provider:'claude.ai',transport:'persistent-browser-session',api_required:false,zero_cost_api_path:true,started_at:startedAt,completed_at:new Date().toISOString(),expected_checksum:EXPECTED,actual_checksum:actual,stages:{master:true,shard_a:true,shard_b:true,shard_c:true,final:true},certified:passed};
  const file=path.join(OUT_DIR,`${TEST_ID}-${nonce}.json`);
  fs.writeFileSync(file,JSON.stringify(cert,null,2));
  console.log('');
  console.log(`CLAUDE_CERTIFIED=${passed?'true':'false'}`);
  console.log(`TEST_ID=${TEST_ID}`);
  console.log(`NONCE=${nonce}`);
  console.log(`EXPECTED_CHECKSUM=${EXPECTED}`);
  console.log(`ACTUAL_CHECKSUM=${actual}`);
  console.log(`CERTIFICATE=${file}`);
  if(!passed)process.exitCode=2;
  await page.close().catch(()=>{});
  await browser.close().catch(()=>{});
}

main().catch(err=>{console.error('CLAUDE_CERTIFIED=false');console.error(`ERROR=${err.message}`);process.exit(1);});
