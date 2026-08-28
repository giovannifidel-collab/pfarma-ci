import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const CDP=process.env.GEMINI_LAB_CDP_URL||'http://127.0.0.1:9225';
const OUT_DIR=process.env.GEMINI_LAB_CERT_DIR||path.resolve('certifications');
const TEST_ID='HIVE-GEMINI-STRESS-0002';
const nonce=crypto.randomBytes(4).toString('hex').toUpperCase();
const MASTER={salt:7919,coeff:[17,29,43]};
const SHARDS={A:[311,7,19,23,5],B:[41,53,67,71,73],C:[79,83,89,97,101]};
const SUMS={A:SHARDS.A.reduce((a,b)=>a+b,0),B:SHARDS.B.reduce((a,b)=>a+b,0),C:SHARDS.C.reduce((a,b)=>a+b,0)};
const EXPECTED=MASTER.salt+MASTER.coeff[0]*SUMS.A+MASTER.coeff[1]*SUMS.B+MASTER.coeff[2]*SUMS.C;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const log=(...x)=>console.log(new Date().toISOString(),...x);

async function composer(page){
  const selectors=[
    'rich-textarea div[contenteditable="true"]',
    'div.ql-editor[contenteditable="true"]',
    'div[contenteditable="true"][aria-label*="prompt" i]',
    'textarea[aria-label*="prompt" i]',
    'div[contenteditable="true"]',
    'textarea'
  ];
  for(const sel of selectors){
    const all=page.locator(sel);
    const n=await all.count().catch(()=>0);
    for(let i=n-1;i>=0;i--){
      const loc=all.nth(i);
      if(await loc.isVisible().catch(()=>false))return loc;
    }
  }
  return null;
}

async function bodyText(page){ return page.locator('body').innerText().catch(()=> ''); }
function literalCount(text,token){ return token ? text.split(token).length-1 : 0; }

async function assistantText(page){
  const selectors=[
    'message-content','model-response','.model-response-text',
    '[data-test-id*="model-response" i]',
    '[data-message-author-role="model"]','[data-message-author-role="assistant"]'
  ];
  const chunks=[];
  for(const sel of selectors){
    const all=page.locator(sel);
    const n=await all.count().catch(()=>0);
    for(let i=0;i<n;i++){
      const t=await all.nth(i).innerText().catch(()=> '');
      if(t)chunks.push(t);
    }
  }
  return [...new Set(chunks)].join('\n');
}

async function send(page,text){
  const c=await composer(page);
  if(!c)throw new Error('GEMINI_NOT_AUTHENTICATED_OR_COMPOSER_NOT_FOUND');
  await c.click();
  const tag=await c.evaluate(el=>el.tagName.toLowerCase()).catch(()=> 'div');
  if(tag==='textarea')await c.fill(text);
  else{
    await c.press(process.platform==='darwin'?'Meta+A':'Control+A').catch(()=>{});
    await c.fill(text).catch(async()=>c.evaluate((el,t)=>{
      el.innerText=t;
      el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:t}));
    },text));
  }
  await c.press('Enter');
}

async function waitForAssistantExact(page,expected,beforeAssistant,beforeBody,timeout=90000){
  const started=Date.now();
  while(Date.now()-started<timeout){
    const a=await assistantText(page);
    if(a && literalCount(a,expected)>beforeAssistant){ await sleep(1000); return 'assistant-container'; }
    const b=await bodyText(page);
    if(literalCount(b,expected)>=beforeBody+2){ await sleep(1000); return 'body-occurrence-fallback'; }
    await sleep(900);
  }
  throw new Error(`TIMEOUT_WAITING_FOR_EXACT_GEMINI_RESPONSE_${expected}`);
}

async function stage(page,label,prompt,expectedEcho){
  const beforeAssistant=literalCount(await assistantText(page),expectedEcho);
  const beforeBody=literalCount(await bodyText(page),expectedEcho);
  log('SEND',label);
  await send(page,prompt);
  const validation=await waitForAssistantExact(page,expectedEcho,beforeAssistant,beforeBody);
  log('PASS',label,validation,'exact-data-echo');
}

async function waitFinal(page,timeout=120000){
  const started=Date.now();
  const regex=new RegExp(`GEMINI_CERT_RESULT:${nonce}:(\\d+):(\\d+):(\\d+):(\\d+)`);
  while(Date.now()-started<timeout){
    const a=await assistantText(page);
    let m=regex.exec(a);
    if(m)return {validation:'assistant-container',sums:{A:Number(m[1]),B:Number(m[2]),C:Number(m[3])},checksum:Number(m[4])};
    const b=await bodyText(page);
    m=regex.exec(b);
    if(m)return {validation:'body-fallback',sums:{A:Number(m[1]),B:Number(m[2]),C:Number(m[3])},checksum:Number(m[4])};
    await sleep(1000);
  }
  throw new Error(`TIMEOUT_WAITING_FOR_GEMINI_CERT_RESULT_${nonce}`);
}

async function main(){
  fs.mkdirSync(OUT_DIR,{recursive:true});
  const startedAt=new Date().toISOString();
  log(`START ${TEST_ID} nonce=${nonce} expected=${EXPECTED} sums=${SUMS.A},${SUMS.B},${SUMS.C}`);

  const browser=await chromium.connectOverCDP(CDP);
  const context=browser.contexts()[0]||await browser.newContext();
  const page=await context.newPage();
  await page.goto('https://gemini.google.com/app',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(2500);
  if(!await composer(page))throw new Error('GEMINI_NOT_AUTHENTICATED_OR_COMPOSER_NOT_FOUND');

  const masterEcho=`ACK_MASTER:${nonce}:${MASTER.salt}:${MASTER.coeff.join(',')}`;
  await stage(page,'MASTER',[
    `${TEST_ID} / ${nonce}`,
    'Memorizza esattamente questo MASTER per un test multi-turn. Non calcolare ancora il risultato finale.',
    `SALT=${MASTER.salt}`,
    `COEFF_A=${MASTER.coeff[0]}`,
    `COEFF_B=${MASTER.coeff[1]}`,
    `COEFF_C=${MASTER.coeff[2]}`,
    `Per confermare i dati ricevuti, rispondi ESATTAMENTE: ${masterEcho}`
  ].join('\n'),masterEcho);

  const echoA=`ACK_A:${nonce}:${SHARDS.A.join(',')}`;
  await stage(page,'SHARD_A',[`${TEST_ID} / ${nonce}`,`SHARD_A=${SHARDS.A.join(',')}`,`Memorizzalo esattamente e rispondi ESATTAMENTE: ${echoA}`].join('\n'),echoA);

  const echoB=`ACK_B:${nonce}:${SHARDS.B.join(',')}`;
  await stage(page,'SHARD_B',[`${TEST_ID} / ${nonce}`,`SHARD_B=${SHARDS.B.join(',')}`,`Memorizzalo esattamente e rispondi ESATTAMENTE: ${echoB}`].join('\n'),echoB);

  const echoC=`ACK_C:${nonce}:${SHARDS.C.join(',')}`;
  await stage(page,'SHARD_C',[`${TEST_ID} / ${nonce}`,`SHARD_C=${SHARDS.C.join(',')}`,`Memorizzalo esattamente e rispondi ESATTAMENTE: ${echoC}`].join('\n'),echoC);

  log('SEND FINAL');
  await send(page,[
    `${TEST_ID} / ${nonce}`,
    'Ora usa SOLO il MASTER e i tre shard memorizzati nei messaggi precedenti.',
    'Calcola separatamente SUM_A, SUM_B, SUM_C e poi CHECKSUM = SALT + COEFF_A*SUM_A + COEFF_B*SUM_B + COEFF_C*SUM_C.',
    'Non aggiungere spiegazioni.',
    `Rispondi ESATTAMENTE nel formato: GEMINI_CERT_RESULT:${nonce}:<SUM_A>:<SUM_B>:<SUM_C>:<CHECKSUM>`
  ].join('\n'));

  const final=await waitFinal(page);
  const passed=final.sums.A===SUMS.A && final.sums.B===SUMS.B && final.sums.C===SUMS.C && final.checksum===EXPECTED;
  const cert={
    test_id:TEST_ID,nonce,provider:'gemini.google.com',transport:'persistent-browser-session',
    api_required:false,zero_cost_api_path:true,started_at:startedAt,completed_at:new Date().toISOString(),
    expected_sums:SUMS,actual_sums:final.sums,expected_checksum:EXPECTED,actual_checksum:final.checksum,
    stages:{master:true,shard_a:true,shard_b:true,shard_c:true,final:true},
    response_validation:final.validation,stage_validation:'exact-data-echo',certified:passed
  };
  const file=path.join(OUT_DIR,`${TEST_ID}-${nonce}.json`);
  fs.writeFileSync(file,JSON.stringify(cert,null,2));

  console.log('');
  console.log(`GEMINI_CERTIFIED=${passed?'true':'false'}`);
  console.log(`TEST_ID=${TEST_ID}`);
  console.log(`NONCE=${nonce}`);
  console.log(`EXPECTED_SUMS=${SUMS.A},${SUMS.B},${SUMS.C}`);
  console.log(`ACTUAL_SUMS=${final.sums.A},${final.sums.B},${final.sums.C}`);
  console.log(`EXPECTED_CHECKSUM=${EXPECTED}`);
  console.log(`ACTUAL_CHECKSUM=${final.checksum}`);
  console.log(`CERTIFICATE=${file}`);
  if(!passed)process.exitCode=2;

  await page.close().catch(()=>{});
  await browser.close().catch(()=>{});
}

main().catch(err=>{
  console.error('GEMINI_CERTIFIED=false');
  console.error(`ERROR=${err.message}`);
  process.exit(1);
});
