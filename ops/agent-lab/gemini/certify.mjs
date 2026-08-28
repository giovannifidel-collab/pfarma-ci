import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const CDP=process.env.GEMINI_LAB_CDP_URL||'http://127.0.0.1:9225';
const OUT_DIR=process.env.GEMINI_LAB_CERT_DIR||path.resolve('certifications');
const TEST_ID='HIVE-GEMINI-STRESS-0001';
const nonce=crypto.randomBytes(4).toString('hex').toUpperCase();
const MASTER={salt:7919,coeff:[17,29,43]};
const SHARDS={A:[311,7,19,23,5],B:[41,53,67,71,73],C:[79,83,89,97,101]};
const EXPECTED=MASTER.salt+MASTER.coeff[0]*SHARDS.A.reduce((a,b)=>a+b,0)+MASTER.coeff[1]*SHARDS.B.reduce((a,b)=>a+b,0)+MASTER.coeff[2]*SHARDS.C.reduce((a,b)=>a+b,0);
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

async function bodyText(page){
  return page.locator('body').innerText().catch(()=> '');
}

function literalCount(text,token){
  if(!token)return 0;
  return text.split(token).length-1;
}

async function assistantText(page){
  const selectors=[
    'message-content',
    'model-response',
    '.model-response-text',
    '[data-test-id*="model-response" i]',
    '[data-message-author-role="model"]',
    '[data-message-author-role="assistant"]'
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

async function waitForAssistantToken(page,token,beforeAssistant,beforeBody,timeout=90000){
  const started=Date.now();
  while(Date.now()-started<timeout){
    const a=await assistantText(page);
    if(a && literalCount(a,token)>beforeAssistant){
      await sleep(1200);
      return 'assistant-container';
    }
    const b=await bodyText(page);
    // Fallback: user prompt adds one occurrence, Gemini answer adds another.
    if(literalCount(b,token)>=beforeBody+2){
      await sleep(1200);
      return 'body-occurrence-fallback';
    }
    await sleep(1000);
  }
  throw new Error(`TIMEOUT_WAITING_FOR_GEMINI_ASSISTANT_TOKEN_${token}`);
}

async function stage(page,label,prompt,ackToken){
  const beforeAssistant=literalCount(await assistantText(page),ackToken);
  const beforeBody=literalCount(await bodyText(page),ackToken);
  log('SEND',label);
  await send(page,prompt);
  const validation=await waitForAssistantToken(page,ackToken,beforeAssistant,beforeBody);
  log('PASS',label,validation);
}

async function waitFinal(page,regex,timeout=120000){
  const started=Date.now();
  while(Date.now()-started<timeout){
    const a=await assistantText(page);
    let m=regex.exec(a);
    if(m)return {match:m,validation:'assistant-container'};
    const b=await bodyText(page);
    m=regex.exec(b);
    if(m)return {match:m,validation:'body-fallback'};
    await sleep(1000);
  }
  throw new Error(`TIMEOUT_WAITING_FOR_${regex}`);
}

async function main(){
  fs.mkdirSync(OUT_DIR,{recursive:true});
  const startedAt=new Date().toISOString();
  log(`START ${TEST_ID} nonce=${nonce} expected=${EXPECTED}`);

  const browser=await chromium.connectOverCDP(CDP);
  const context=browser.contexts()[0]||await browser.newContext();
  const page=await context.newPage();
  await page.goto('https://gemini.google.com/app',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(2500);

  if(!await composer(page))throw new Error('GEMINI_NOT_AUTHENTICATED_OR_COMPOSER_NOT_FOUND');

  const masterAck=`ACK_MASTER:${nonce}`;
  await stage(page,'MASTER',[
    `${TEST_ID} / ${nonce}`,
    'Memorizza questo MASTER per un test multi-turn. Non calcolare ancora il risultato finale.',
    `SALT=${MASTER.salt}`,
    `COEFF_A=${MASTER.coeff[0]}`,
    `COEFF_B=${MASTER.coeff[1]}`,
    `COEFF_C=${MASTER.coeff[2]}`,
    `Quando hai memorizzato, rispondi ESATTAMENTE: ${masterAck}`
  ].join('\n'),masterAck);

  const ackA=`ACK_A:${nonce}`;
  await stage(page,'SHARD_A',[`${TEST_ID} / ${nonce}`,`SHARD_A=${SHARDS.A.join(',')}`,`Memorizzalo e rispondi ESATTAMENTE: ${ackA}`].join('\n'),ackA);

  const ackB=`ACK_B:${nonce}`;
  await stage(page,'SHARD_B',[`${TEST_ID} / ${nonce}`,`SHARD_B=${SHARDS.B.join(',')}`,`Memorizzalo e rispondi ESATTAMENTE: ${ackB}`].join('\n'),ackB);

  const ackC=`ACK_C:${nonce}`;
  await stage(page,'SHARD_C',[`${TEST_ID} / ${nonce}`,`SHARD_C=${SHARDS.C.join(',')}`,`Memorizzalo e rispondi ESATTAMENTE: ${ackC}`].join('\n'),ackC);

  log('SEND FINAL');
  await send(page,[
    `${TEST_ID} / ${nonce}`,
    'Ora usa SOLO il MASTER e i tre shard ricevuti nei messaggi precedenti.',
    'Calcola: CHECKSUM = SALT + COEFF_A*SUM(SHARD_A) + COEFF_B*SUM(SHARD_B) + COEFF_C*SUM(SHARD_C).',
    'Non aggiungere spiegazioni.',
    `Rispondi ESATTAMENTE nel formato: GEMINI_CERT_RESULT:${nonce}:<CHECKSUM>`
  ].join('\n'));

  const final=await waitFinal(page,new RegExp(`GEMINI_CERT_RESULT:${nonce}:(\\d+)`));
  const actual=Number(final.match[1]);
  const passed=actual===EXPECTED;
  const cert={
    test_id:TEST_ID,
    nonce,
    provider:'gemini.google.com',
    transport:'persistent-browser-session',
    api_required:false,
    zero_cost_api_path:true,
    started_at:startedAt,
    completed_at:new Date().toISOString(),
    expected_checksum:EXPECTED,
    actual_checksum:actual,
    stages:{master:true,shard_a:true,shard_b:true,shard_c:true,final:true},
    response_validation:final.validation,
    certified:passed
  };
  const file=path.join(OUT_DIR,`${TEST_ID}-${nonce}.json`);
  fs.writeFileSync(file,JSON.stringify(cert,null,2));

  console.log('');
  console.log(`GEMINI_CERTIFIED=${passed?'true':'false'}`);
  console.log(`TEST_ID=${TEST_ID}`);
  console.log(`NONCE=${nonce}`);
  console.log(`EXPECTED_CHECKSUM=${EXPECTED}`);
  console.log(`ACTUAL_CHECKSUM=${actual}`);
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
