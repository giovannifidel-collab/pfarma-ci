import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const CDP=process.env.GROK_LAB_CDP_URL||'http://127.0.0.1:9226';
const OUT=path.resolve('certifications');
const TEST='HIVE-GROK-STRESS-0007';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const log=(...x)=>console.log(new Date().toISOString(),...x);

const DATASETS=[
 {salt:7919,coeff:{A:17,B:29,C:43},shards:{A:[311,7,19,23,5],B:[41,53,67,71,73],C:[79,83,89,97,101]}},
 {salt:6421,coeff:{A:23,B:31,C:37},shards:{A:[107,13,29,31,17],B:[47,59,61,71,11],C:[83,89,97,19,23]}},
 {salt:4813,coeff:{A:19,B:41,C:47},shards:{A:[127,37,43,53,61],B:[17,67,79,83,89],C:[97,101,103,29,31]}}
];

const EDITABLE_SELECTORS=[
 'textarea[data-testid="grok-compose-input"]',
 '[data-testid="grokInput"] textarea',
 '[data-testid="grokInput"] [contenteditable="true"]',
 'div[contenteditable="true"][data-lexical-editor="true"]',
 'textarea[aria-label*="Ask" i]',
 'textarea[placeholder*="Ask" i]',
 'div[contenteditable="true"]',
 '[data-testid="grokInput"]'
];
const SEND_SELECTORS=[
 'button[data-testid="chat-submit"]',
 'button[aria-label="Submit"]',
 'button[aria-label*="Send" i]',
 'button[aria-label*="Submit" i]',
 'button[data-testid*="send" i]',
 'button[data-testid*="submit" i]',
 'button[type="submit"]'
];
const STOP_SELECTORS=[
 'button[aria-label*="Stop" i]',
 'button[data-testid*="stop" i]',
 'button[title*="Stop" i]'
];

async function firstVisible(page,sels){
 for(const sel of sels){
   const list=page.locator(sel), n=await list.count().catch(()=>0);
   for(let i=n-1;i>=0;i--){
     const x=list.nth(i);
     if(await x.isVisible().catch(()=>false)) return x;
   }
 }
 return null;
}
async function firstEnabled(page,sels){
 for(const sel of sels){
   const list=page.locator(sel), n=await list.count().catch(()=>0);
   for(let i=n-1;i>=0;i--){
     const x=list.nth(i);
     if(await x.isVisible().catch(()=>false) && await x.isEnabled().catch(()=>false)) return x;
   }
 }
 return null;
}
async function editable(page){
 const x=await firstVisible(page,EDITABLE_SELECTORS);
 if(!x) return null;
 const info=await x.evaluate(el=>({
   tag:el.tagName.toLowerCase(),
   contenteditable:el.getAttribute('contenteditable'),
   testid:el.getAttribute('data-testid'),
   aria:el.getAttribute('aria-label')
 })).catch(()=>({tag:'unknown'}));
 if(info.tag==='textarea'||info.tag==='input'||info.contenteditable==='true') return x;
 const child=x.locator('textarea,[contenteditable="true"]').last();
 if(await child.isVisible().catch(()=>false)) return child;
 return null;
}
async function bodyText(page){return page.locator('body').innerText().catch(()=> '');}
async function editorText(x){
 const tag=await x.evaluate(el=>el.tagName.toLowerCase()).catch(()=> 'div');
 return ['textarea','input'].includes(tag)?x.inputValue().catch(()=> ''):x.innerText().catch(()=> '');
}
const literalCount=(txt,tok)=>tok?txt.split(tok).length-1:0;
async function isGenerating(page){return !!(await firstVisible(page,STOP_SELECTORS));}

async function settle(page,quietMs=1400,maxMs=12000){
 let last=await bodyText(page), changed=Date.now(); const start=Date.now();
 while(Date.now()-start<maxMs){
   await sleep(300); const now=await bodyText(page);
   if(now!==last){last=now;changed=Date.now();}
   if(Date.now()-changed>=quietMs) return;
 }
}
async function waitIdle(page,maxMs=120000){
 const start=Date.now();
 while(Date.now()-start<maxMs){
   if(!(await isGenerating(page))){
     const c=await editable(page).catch(()=>null);
     if(c){await settle(page,900,4000);return;}
   }
   await sleep(500);
 }
 throw new Error('GROK_UI_NOT_IDLE');
}

async function clearEditor(c){
 await c.click();
 const tag=await c.evaluate(el=>el.tagName.toLowerCase()).catch(()=> 'div');
 if(['textarea','input'].includes(tag)){
   await c.fill('');
 }else{
   await c.press('Control+A').catch(()=>{});
   await c.press('Backspace').catch(()=>{});
   const remain=(await editorText(c)).trim();
   if(remain) await c.evaluate(el=>{el.focus();document.execCommand('selectAll',false);document.execCommand('delete',false);}).catch(()=>{});
 }
}

async function typeLikeUser(page,c,text){
 await clearEditor(c);
 const lines=text.split('\n');
 for(let i=0;i<lines.length;i++){
   if(lines[i]) await c.pressSequentially(lines[i],{delay:1});
   if(i<lines.length-1) await c.press('Shift+Enter');
 }
 const got=(await editorText(c)).trim();
 if(got.length<5) throw new Error('GROK_NATIVE_INPUT_EMPTY');
 return got;
}

async function waitSubmit(page,maxMs=20000){
 const start=Date.now();
 while(Date.now()-start<maxMs){
   const btn=await firstEnabled(page,SEND_SELECTORS);
   if(btn) return btn;
   await sleep(250);
 }
 return null;
}

async function diagnostic(page,c){
 const text=(await editorText(c).catch(()=> '')).trim();
 const anyBtn=await firstVisible(page,SEND_SELECTORS);
 const btn=anyBtn?await anyBtn.evaluate(el=>({disabled:el.disabled,ariaDisabled:el.getAttribute('aria-disabled'),testid:el.getAttribute('data-testid'),aria:el.getAttribute('aria-label')})).catch(()=>null):null;
 const ed=await c.evaluate(el=>({tag:el.tagName.toLowerCase(),contenteditable:el.getAttribute('contenteditable'),testid:el.getAttribute('data-testid'),aria:el.getAttribute('aria-label')})).catch(()=>null);
 return {text_len:text.length,generating:await isGenerating(page),editor:ed,button:btn};
}

async function send(page,text){
 await waitIdle(page);
 let c=await editable(page); if(!c) throw new Error('GROK_EDITABLE_NOT_FOUND');
 let inserted=await typeLikeUser(page,c,text);
 let btn=await waitSubmit(page,20000);
 if(!btn){
   log('NATIVE_REARM',`text_len=${inserted.length}`);
   c=await editable(page); if(!c) throw new Error('GROK_EDITABLE_LOST');
   await c.click();
   await c.pressSequentially(' ',{delay:1});
   await c.press('Backspace');
   inserted=(await editorText(c)).trim();
   btn=await waitSubmit(page,10000);
 }
 if(!btn){
   const d=await diagnostic(page,c);
   throw new Error(`GROK_SUBMIT_NOT_READY_NATIVE ${JSON.stringify(d)}`);
 }
 await btn.click({timeout:5000});
 log('SUBMIT native-button');
 const start=Date.now();
 while(Date.now()-start<15000){
   if((await editorText(c).catch(()=> '')).trim().length<5) return;
   await sleep(250);
 }
 throw new Error('GROK_NATIVE_PROMPT_NOT_SUBMITTED');
}

async function freshPage(context){
 const old=context.pages().filter(p=>p.url().includes('grok.com'));
 const page=await context.newPage();
 await page.goto('https://grok.com/',{waitUntil:'domcontentloaded',timeout:60000});
 const start=Date.now();
 while(Date.now()-start<45000){
   if(await editable(page).catch(()=>null)){
     for(const p of old) await p.close().catch(()=>{});
     return page;
   }
   await sleep(750);
 }
 throw new Error(`GROK_FRESH_CHAT_NOT_READY url=${page.url()}`);
}

async function echoStage(page,label,prompt,echo){
 const before=literalCount(await bodyText(page),echo);
 log('SEND',label); await send(page,prompt);
 const start=Date.now();
 while(Date.now()-start<90000){
   if(literalCount(await bodyText(page),echo)>=before+2){
     await waitIdle(page); log('PASS',label,'assistant-echo-verified'); return;
   }
   await sleep(700);
 }
 throw new Error(`TIMEOUT_${label}_ASSISTANT_ECHO`);
}

async function askNumber(page,nonce,label,instruction,recheck=false){
 const marker=`GROK_${recheck?'RECHECK_':''}${label}:${nonce}:`;
 log('SEND',recheck?`RECHECK_${label}`:label);
 const extra=recheck?'Il valore precedente non supera un controllo di coerenza. Ricontrolla da zero usando i dati originali. Non ti fornisco il valore atteso.':'';
 await send(page,[`${TEST} / ${nonce}`,instruction,extra,'Nessuna spiegazione.',`Rispondi ESATTAMENTE: ${marker}<numero>`].filter(Boolean).join('\n'));
 const re=new RegExp(`${marker}(\\d+)`); const start=Date.now();
 while(Date.now()-start<90000){
   const m=re.exec(await bodyText(page));
   if(m){const v=Number(m[1]);await waitIdle(page);log('RESULT',recheck?`RECHECK_${label}`:label,v);return v;}
   await sleep(700);
 }
 throw new Error(`TIMEOUT_${label}`);
}

function expected(d){
 const sums={},terms={};
 for(const k of ['A','B','C']){sums[k]=d.shards[k].reduce((a,b)=>a+b,0);terms[k]=d.coeff[k]*sums[k];}
 return {sums,terms,checksum:d.salt+terms.A+terms.B+terms.C};
}
async function checkedNumber(page,nonce,label,instruction,want){
 const first=await askNumber(page,nonce,label,instruction,false);
 if(first===want) return {first,final:first,rechecked:false,ok:true};
 const second=await askNumber(page,nonce,label,instruction,true);
 return {first,final:second,rechecked:true,ok:second===want};
}

async function trial(context,index,d){
 const nonce=crypto.randomBytes(4).toString('hex').toUpperCase();
 const exp=expected(d); const page=await freshPage(context);
 log('TRIAL_START',index,`nonce=${nonce}`,`expected=${exp.checksum}`);
 const master=`ACK_MASTER:${nonce}:${d.salt}:${d.coeff.A},${d.coeff.B},${d.coeff.C}`;
 await echoStage(page,'MASTER',[`${TEST} / ${nonce}`,`SALT=${d.salt}`,`COEFF_A=${d.coeff.A}`,`COEFF_B=${d.coeff.B}`,`COEFF_C=${d.coeff.C}`,`Memorizza e rispondi ESATTAMENTE: ${master}`].join('\n'),master);
 for(const k of ['A','B','C']){
   const ack=`ACK_${k}:${nonce}:${d.shards[k].join(',')}`;
   await echoStage(page,`SHARD_${k}`,[`${TEST} / ${nonce}`,`SHARD_${k}=${d.shards[k].join(',')}`,`Memorizza e rispondi ESATTAMENTE: ${ack}`].join('\n'),ack);
 }
 const results={sums:{},terms:{}};
 for(const k of ['A','B','C']) results.sums[k]=await checkedNumber(page,nonce,`SUM_${k}`,`Ricalcola la somma di tutti gli elementi di SHARD_${k} memorizzato.`,exp.sums[k]);
 for(const k of ['A','B','C']) results.terms[k]=await checkedNumber(page,nonce,`TERM_${k}`,`Ricalcola da zero SUM_${k} dal relativo shard, poi calcola COEFF_${k} * SUM_${k}.`,exp.terms[k]);
 results.checksum=await checkedNumber(page,nonce,'CHECKSUM','Ricalcola da zero le tre somme e i tre prodotti dai dati originali, poi calcola SALT + TERM_A + TERM_B + TERM_C.',exp.checksum);
 const fields=[...Object.values(results.sums),...Object.values(results.terms),results.checksum];
 const raw=fields.every(x=>x.first===x.final&&x.ok), verified=fields.every(x=>x.ok);
 log('TRIAL_END',index,`RAW_PASS=${raw}`,`VERIFIED_PASS=${verified}`);
 await page.close().catch(()=>{});
 return {index,nonce,expected:exp,results,raw_pass:raw,verified_pass:verified};
}

async function main(){
 fs.mkdirSync(OUT,{recursive:true});
 const browser=await chromium.connectOverCDP(CDP); const context=browser.contexts()[0]||await browser.newContext(); const trials=[];
 for(let i=0;i<DATASETS.length;i++) trials.push(await trial(context,i+1,DATASETS[i]));
 const raw=trials.every(t=>t.raw_pass), verified=trials.every(t=>t.verified_pass), certified=verified;
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
 process.exit(certified?0:2);
}
main().catch(e=>{console.error('GROK_CERTIFIED=false');console.error(`ERROR=${e.message}`);process.exit(1);});
