import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const CDP=process.env.GROK_LAB_CDP_URL||'http://127.0.0.1:9226';
const OUT=path.resolve('certifications');
const TEST='HIVE-GROK-STRESS-0005';
const nonce=crypto.randomBytes(4).toString('hex').toUpperCase();
const MASTER={salt:7919,coeff:{A:17,B:29,C:43}};
const SHARDS={A:[311,7,19,23,5],B:[41,53,67,71,73],C:[79,83,89,97,101]};
const EXPECTED_SUMS={A:365,B:305,C:449};
const EXPECTED_TERMS={A:6205,B:8845,C:19307};
const EXPECTED_CHECKSUM=42276;
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
  return visible(page,['[data-testid="grokInput"]','textarea[data-testid="grok-compose-input"]','textarea[aria-label*="Ask" i]','textarea[placeholder*="Ask" i]','div[contenteditable="true"][data-lexical-editor="true"]','div[contenteditable="true"]','textarea']);
}
async function body(page){ return page.locator('body').innerText().catch(()=> ''); }
const count=(txt,tok)=>tok?txt.split(tok).length-1:0;
async function textOf(c){ const tag=await c.evaluate(el=>el.tagName.toLowerCase()).catch(()=> 'div'); return ['textarea','input'].includes(tag)?c.inputValue().catch(()=> ''):c.innerText().catch(()=> ''); }

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

async function echoStage(page,label,prompt,echo){
  const before=count(await body(page),echo); log('SEND',label); await send(page,prompt);
  const start=Date.now();
  while(Date.now()-start<90000){ if(count(await body(page),echo)>=before+2){ log('PASS',label,'exact-body-echo'); return; } await sleep(800); }
  throw new Error(`TIMEOUT_${label}`);
}

async function numericStage(page,label,instruction){
  const marker=`GROK_${label}:${nonce}:`;
  log('SEND',label);
  await send(page,[`${TEST} / ${nonce}`,instruction,'Calcola autonomamente. Non usare risultati suggeriti. Non aggiungere spiegazioni.',`Rispondi ESATTAMENTE: ${marker}<numero>`].join('\n'));
  const re=new RegExp(`${marker}(\\d+)`);
  const start=Date.now();
  while(Date.now()-start<90000){
    const txt=await body(page); const m=re.exec(txt);
    if(m){ const value=Number(m[1]); log('RESULT',label,value); return value; }
    await sleep(800);
  }
  throw new Error(`TIMEOUT_${label}`);
}

async function findReadyPage(context){
  for(const p of context.pages()) if(p.url().includes('grok.com') && await composer(p).catch(()=>null)) return p;
  const p=await context.newPage();
  await p.goto('https://grok.com/',{waitUntil:'domcontentloaded',timeout:60000});
  const start=Date.now();
  while(Date.now()-start<30000){ if(await composer(p).catch(()=>null)) return p; await sleep(1000); }
  throw new Error(`GROK_NOT_AUTHENTICATED_OR_COMPOSER_NOT_FOUND url=${p.url()}`);
}

async function main(){
  fs.mkdirSync(OUT,{recursive:true});
  log('START',TEST,`nonce=${nonce}`,`expected=${EXPECTED_CHECKSUM}`);
  const browser=await chromium.connectOverCDP(CDP);
  const context=browser.contexts()[0]||await browser.newContext();
  const page=await findReadyPage(context);

  const master=`ACK_MASTER:${nonce}:${MASTER.salt}:${MASTER.coeff.A},${MASTER.coeff.B},${MASTER.coeff.C}`;
  await echoStage(page,'MASTER',[`${TEST} / ${nonce}`,`SALT=${MASTER.salt}`,`COEFF_A=${MASTER.coeff.A}`,`COEFF_B=${MASTER.coeff.B}`,`COEFF_C=${MASTER.coeff.C}`,`Memorizza questi dati e rispondi ESATTAMENTE: ${master}`].join('\n'),master);
  for(const name of ['A','B','C']){
    const data=SHARDS[name]; const echo=`ACK_${name}:${nonce}:${data.join(',')}`;
    await echoStage(page,`SHARD_${name}`,[`${TEST} / ${nonce}`,`SHARD_${name}=${data.join(',')}`,`Memorizzalo e rispondi ESATTAMENTE: ${echo}`].join('\n'),echo);
  }

  const sums={};
  for(const name of ['A','B','C']) sums[name]=await numericStage(page,`SUM_${name}`,`Somma tutti gli elementi di SHARD_${name} memorizzato in precedenza.`);

  const terms={};
  for(const name of ['A','B','C']) terms[name]=await numericStage(page,`TERM_${name}`,`Calcola COEFF_${name} moltiplicato per SUM_${name} usando i dati e il risultato calcolati nei turni precedenti.`);

  const checksum=await numericStage(page,'CHECKSUM','Calcola SALT + TERM_A + TERM_B + TERM_C usando esclusivamente i dati e i risultati dei turni precedenti. Prima di rispondere verifica una seconda volta la somma.');

  const passed=['A','B','C'].every(k=>sums[k]===EXPECTED_SUMS[k] && terms[k]===EXPECTED_TERMS[k]) && checksum===EXPECTED_CHECKSUM;
  const file=path.join(OUT,`${TEST}-${nonce}.json`);
  fs.writeFileSync(file,JSON.stringify({test_id:TEST,nonce,expected_sums:EXPECTED_SUMS,actual_sums:sums,expected_terms:EXPECTED_TERMS,actual_terms:terms,expected_checksum:EXPECTED_CHECKSUM,actual_checksum:checksum,certified:passed},null,2));

  console.log(`GROK_CERTIFIED=${passed}`);
  console.log(`TEST_ID=${TEST}`);
  console.log(`NONCE=${nonce}`);
  console.log(`EXPECTED_SUMS=${EXPECTED_SUMS.A},${EXPECTED_SUMS.B},${EXPECTED_SUMS.C}`);
  console.log(`ACTUAL_SUMS=${sums.A},${sums.B},${sums.C}`);
  console.log(`EXPECTED_TERMS=${EXPECTED_TERMS.A},${EXPECTED_TERMS.B},${EXPECTED_TERMS.C}`);
  console.log(`ACTUAL_TERMS=${terms.A},${terms.B},${terms.C}`);
  console.log(`EXPECTED_CHECKSUM=${EXPECTED_CHECKSUM}`);
  console.log(`ACTUAL_CHECKSUM=${checksum}`);
  console.log(`CERTIFICATE=${file}`);
  if(!passed) process.exitCode=2;
  await browser.close().catch(()=>{});
}

main().catch(e=>{ console.error('GROK_CERTIFIED=false'); console.error(`ERROR=${e.message}`); process.exit(1); });
