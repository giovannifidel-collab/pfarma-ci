import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const CDP=process.env.GROK_LAB_CDP_URL||'http://127.0.0.1:9226';
const OUT=path.resolve('certifications');
const TEST='HIVE-GROK-STRESS-0004';
const nonce=crypto.randomBytes(4).toString('hex').toUpperCase();
const MASTER={salt:7919,coeff:[17,29,43]};
const SHARDS={A:[311,7,19,23,5],B:[41,53,67,71,73],C:[79,83,89,97,101]};
const SUMS={A:365,B:305,C:449};
const TERMS={A:6205,B:8845,C:19307};
const EXPECTED=42276;
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
  log('START',TEST,`nonce=${nonce}`,`expected=${EXPECTED}`);
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

  const marker=`GROK_DIAG_RESULT:${nonce}`;
  log('SEND FINAL_DIAGNOSTIC');
  await send(page,[
    `${TEST} / ${nonce}`,
    'Usa SOLO il MASTER e i tre SHARD memorizzati nei messaggi precedenti.',
    'Calcola autonomamente le tre somme, poi i tre prodotti, poi il checksum finale.',
    'Definizioni: TERM_A=COEFF_A*SUM_A; TERM_B=COEFF_B*SUM_B; TERM_C=COEFF_C*SUM_C; CHECKSUM=SALT+TERM_A+TERM_B+TERM_C.',
    'Non usare valori suggeriti: ricavali dai dati memorizzati.',
    `Rispondi con queste righe e nessuna spiegazione:\n${marker}\nSUM_A=<numero>\nSUM_B=<numero>\nSUM_C=<numero>\nTERM_A=<numero>\nTERM_B=<numero>\nTERM_C=<numero>\nCHECKSUM=<numero>`
  ].join('\n'));

  let txt=''; const start=Date.now();
  while(Date.now()-start<120000){ txt=await body(page); if(txt.includes(marker) && /CHECKSUM=\d+/.test(txt)) break; await sleep(800); }
  if(!txt.includes(marker)) throw new Error('TIMEOUT_FINAL_DIAGNOSTIC');

  const tail=txt.slice(txt.lastIndexOf(marker));
  const get=name=>{ const m=tail.match(new RegExp(`${name}=(\\d+)`)); return m?Number(m[1]):null; };
  const actual={
    sums:{A:get('SUM_A'),B:get('SUM_B'),C:get('SUM_C')},
    terms:{A:get('TERM_A'),B:get('TERM_B'),C:get('TERM_C')},
    checksum:get('CHECKSUM')
  };

  const passed=actual.sums.A===SUMS.A && actual.sums.B===SUMS.B && actual.sums.C===SUMS.C &&
    actual.terms.A===TERMS.A && actual.terms.B===TERMS.B && actual.terms.C===TERMS.C &&
    actual.checksum===EXPECTED;

  const file=path.join(OUT,`${TEST}-${nonce}.json`);
  fs.writeFileSync(file,JSON.stringify({test_id:TEST,nonce,expected_sums:SUMS,actual_sums:actual.sums,expected_terms:TERMS,actual_terms:actual.terms,expected_checksum:EXPECTED,actual_checksum:actual.checksum,certified:passed},null,2));

  console.log(`GROK_CERTIFIED=${passed}`);
  console.log(`TEST_ID=${TEST}`);
  console.log(`NONCE=${nonce}`);
  console.log(`EXPECTED_SUMS=${SUMS.A},${SUMS.B},${SUMS.C}`);
  console.log(`ACTUAL_SUMS=${actual.sums.A},${actual.sums.B},${actual.sums.C}`);
  console.log(`EXPECTED_TERMS=${TERMS.A},${TERMS.B},${TERMS.C}`);
  console.log(`ACTUAL_TERMS=${actual.terms.A},${actual.terms.B},${actual.terms.C}`);
  console.log(`EXPECTED_CHECKSUM=${EXPECTED}`);
  console.log(`ACTUAL_CHECKSUM=${actual.checksum}`);
  console.log(`CERTIFICATE=${file}`);
  if(!passed) process.exitCode=2;
  await browser.close().catch(()=>{});
}

main().catch(e=>{ console.error('GROK_CERTIFIED=false'); console.error(`ERROR=${e.message}`); process.exit(1); });
