import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const CDP=process.env.GROK_LAB_CDP_URL||'http://127.0.0.1:9226';
const OUT=path.resolve('certifications');
const TEST='HIVE-GROK-STRESS-0006R1';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const log=(...x)=>console.log(new Date().toISOString(),...x);

const DATASETS=[
 {salt:7919,coeff:{A:17,B:29,C:43},shards:{A:[311,7,19,23,5],B:[41,53,67,71,73],C:[79,83,89,97,101]}},
 {salt:6421,coeff:{A:23,B:31,C:37},shards:{A:[107,13,29,31,17],B:[47,59,61,71,11],C:[83,89,97,19,23]}},
 {salt:4813,coeff:{A:19,B:41,C:47},shards:{A:[127,37,43,53,61],B:[17,67,79,83,89],C:[97,101,103,29,31]}}
];

async function visible(page,sels){
 for(const s of sels){const a=page.locator(s),n=await a.count().catch(()=>0);for(let i=n-1;i>=0;i--){const x=a.nth(i);if(await x.isVisible().catch(()=>false))return x;}}
 return null;
}
async function visibleEnabled(page,sels){
 for(const s of sels){const a=page.locator(s),n=await a.count().catch(()=>0);for(let i=n-1;i>=0;i--){const x=a.nth(i);if(await x.isVisible().catch(()=>false) && await x.isEnabled().catch(()=>false))return x;}}
 return null;
}
async function composer(page){return visible(page,['[data-testid="grokInput"]','textarea[data-testid="grok-compose-input"]','textarea[aria-label*="Ask" i]','textarea[placeholder*="Ask" i]','div[contenteditable="true"][data-lexical-editor="true"]','div[contenteditable="true"]','textarea']);}
async function body(page){return page.locator('body').innerText().catch(()=> '');}
async function textOf(c){const tag=await c.evaluate(e=>e.tagName.toLowerCase()).catch(()=> 'div');return ['textarea','input'].includes(tag)?c.inputValue().catch(()=> ''):c.innerText().catch(()=> '');}
const literalCount=(txt,tok)=>tok?txt.split(tok).length-1:0;
const SEND_SELECTORS=['button[aria-label="Submit"]','button[aria-label*="Send" i]','button[aria-label*="Submit" i]','button[data-testid="chat-submit"]','button[data-testid*="send" i]','button[data-testid*="submit" i]','button[type="submit"]'];

async function send(page,text){
 const c=await composer(page); if(!c)throw new Error('GROK_COMPOSER_NOT_FOUND');
 await c.click();
 const tag=await c.evaluate(e=>e.tagName.toLowerCase()).catch(()=> 'div');
 if(['textarea','input'].includes(tag)) await c.fill(text);
 else await c.fill(text).catch(async()=>c.evaluate((e,t)=>{e.focus();e.textContent=t;e.dispatchEvent(new InputEvent('input',{bubbles:true,composed:true,inputType:'insertText',data:t}));},text));

 const inserted=(await textOf(c).catch(()=> '')).trim();
 if(inserted.length<5) throw new Error('GROK_TEXT_NOT_INSERTED');

 let btn=null;
 const readyStart=Date.now();
 while(Date.now()-readyStart<7000){
   btn=await visibleEnabled(page,SEND_SELECTORS);
   if(btn)break;
   await sleep(200);
 }

 if(btn){
   await btn.click({timeout:5000});
   log('SUBMIT button-enabled');
 }else{
   await c.press('Enter');
   log('SUBMIT enter-fallback');
 }

 const st=Date.now();
 while(Date.now()-st<10000){
   const current=await textOf(c).catch(()=> '');
   if(current.trim().length<5)return;
   await sleep(250);
 }
 throw new Error('GROK_PROMPT_NOT_SUBMITTED');
}

async function freshPage(context){
 for(const p of context.pages())if(p.url().includes('grok.com'))await p.close().catch(()=>{});
 const p=await context.newPage();
 await p.goto('https://grok.com/',{waitUntil:'domcontentloaded',timeout:60000});
 const st=Date.now();
 while(Date.now()-st<30000){if(await composer(p).catch(()=>null))return p;await sleep(1000);}
 throw new Error(`GROK_FRESH_CHAT_NOT_READY url=${p.url()}`);
}

async function echoStage(page,label,prompt,echo){
 const before=literalCount(await body(page),echo);
 log('SEND',label);
 await send(page,prompt);
 const st=Date.now();
 while(Date.now()-st<90000){
   const now=literalCount(await body(page),echo);
   if(now>=before+2){log('PASS',label,'assistant-echo-verified');return;}
   await sleep(700);
 }
 throw new Error(`TIMEOUT_${label}_ASSISTANT_ECHO`);
}

async function askNumber(page,nonce,label,instruction,recheck=false){
 const marker=`GROK_${recheck?'RECHECK_':''}${label}:${nonce}:`;
 log('SEND',recheck?`RECHECK_${label}`:label);
 const extra=recheck?'Il valore precedente non supera un controllo di coerenza. Ricontrolla da zero usando i dati originali. Non ti fornisco il valore atteso.':'';
 await send(page,[`${TEST} / ${nonce}`,instruction,extra,'Nessuna spiegazione.',`Rispondi ESATTAMENTE: ${marker}<numero>`].filter(Boolean).join('\n'));
 const re=new RegExp(`${marker}(\\d+)`),st=Date.now();
 while(Date.now()-st<90000){const m=re.exec(await body(page));if(m){const v=Number(m[1]);log('RESULT',recheck?`RECHECK_${label}`:label,v);return v;}await sleep(700);}
 throw new Error(`TIMEOUT_${label}`);
}

function expected(d){const sums={},terms={};for(const k of ['A','B','C']){sums[k]=d.shards[k].reduce((a,b)=>a+b,0);terms[k]=d.coeff[k]*sums[k];}return {sums,terms,checksum:d.salt+terms.A+terms.B+terms.C};}
async function checkedNumber(page,nonce,label,instruction,want){
 const first=await askNumber(page,nonce,label,instruction,false);
 if(first===want)return {first,final:first,rechecked:false,ok:true};
 const second=await askNumber(page,nonce,label,instruction,true);
 return {first,final:second,rechecked:true,ok:second===want};
}

async function trial(context,index,d){
 const nonce=crypto.randomBytes(4).toString('hex').toUpperCase();
 const exp=expected(d);
 const page=await freshPage(context);
 log('TRIAL_START',index,`nonce=${nonce}`,`expected=${exp.checksum}`);

 const master=`ACK_MASTER:${nonce}:${d.salt}:${d.coeff.A},${d.coeff.B},${d.coeff.C}`;
 await echoStage(page,'MASTER',[`${TEST} / ${nonce}`,`SALT=${d.salt}`,`COEFF_A=${d.coeff.A}`,`COEFF_B=${d.coeff.B}`,`COEFF_C=${d.coeff.C}`,`Memorizza e rispondi ESATTAMENTE: ${master}`].join('\n'),master);
 for(const k of ['A','B','C']){
   const e=`ACK_${k}:${nonce}:${d.shards[k].join(',')}`;
   await echoStage(page,`SHARD_${k}`,[`${TEST} / ${nonce}`,`SHARD_${k}=${d.shards[k].join(',')}`,`Memorizza e rispondi ESATTAMENTE: ${e}`].join('\n'),e);
 }

 const results={sums:{},terms:{}};
 for(const k of ['A','B','C'])results.sums[k]=await checkedNumber(page,nonce,`SUM_${k}`,`Ricalcola la somma di tutti gli elementi di SHARD_${k} memorizzato.`,exp.sums[k]);
 for(const k of ['A','B','C'])results.terms[k]=await checkedNumber(page,nonce,`TERM_${k}`,`Ricalcola da zero SUM_${k} dal relativo shard, poi calcola COEFF_${k} * SUM_${k}.`,exp.terms[k]);
 results.checksum=await checkedNumber(page,nonce,'CHECKSUM','Ricalcola da zero le tre somme e i tre prodotti dai dati originali, poi calcola SALT + TERM_A + TERM_B + TERM_C.',exp.checksum);

 const fields=[...Object.values(results.sums),...Object.values(results.terms),results.checksum];
 const raw=fields.every(x=>x.first===x.final&&x.ok);
 const verified=fields.every(x=>x.ok);
 log('TRIAL_END',index,`RAW_PASS=${raw}`,`VERIFIED_PASS=${verified}`);
 await page.close().catch(()=>{});
 return {index,nonce,expected:exp,results,raw_pass:raw,verified_pass:verified};
}

async function main(){
 fs.mkdirSync(OUT,{recursive:true});
 const browser=await chromium.connectOverCDP(CDP);
 const context=browser.contexts()[0]||await browser.newContext();
 const trials=[];
 for(let i=0;i<DATASETS.length;i++)trials.push(await trial(context,i+1,DATASETS[i]));
 const raw=trials.every(t=>t.raw_pass);
 const verified=trials.every(t=>t.verified_pass);
 const certified=verified;
 const mode=raw?'RAW_CERTIFIED':verified?'VERIFIER_CERTIFIED':'NOT_CERTIFIED';
 const file=path.join(OUT,`${TEST}-${Date.now()}.json`);
 fs.writeFileSync(file,JSON.stringify({test_id:TEST,trials,raw_pass:raw,verified_pass:verified,certification_mode:mode,certified},null,2));
 console.log(`GROK_CERTIFIED=${certified}`);
 console.log(`TEST_ID=${TEST}`);
 console.log(`TRIALS=${trials.length}`);
 console.log(`RAW_PASS=${raw}`);
 console.log(`VERIFIED_PASS=${verified}`);
 console.log(`CERTIFICATION_MODE=${mode}`);
 console.log(`CERTIFICATE=${file}`);
 if(!certified)process.exitCode=2;
 await browser.close().catch(()=>{});
}
main().catch(e=>{console.error('GROK_CERTIFIED=false');console.error(`ERROR=${e.message}`);process.exit(1);});
