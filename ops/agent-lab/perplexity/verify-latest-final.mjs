import fs from 'node:fs';
import path from 'node:path';

const CDP=process.env.PERPLEXITY_LAB_CDP_URL||'http://127.0.0.1:9230';
const CERT_DIR=process.env.PERPLEXITY_LAB_CERT_DIR||path.resolve('certifications');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

const files=fs.readdirSync(CERT_DIR)
  .filter(f=>/^HIVE-PERPLEXITY-STRESS-0001-.*\.json$/.test(f))
  .map(f=>({f,p:path.join(CERT_DIR,f),mtime:fs.statSync(path.join(CERT_DIR,f)).mtimeMs}))
  .sort((a,b)=>b.mtime-a.mtime);
if(!files.length) throw new Error('NO_PERPLEXITY_CERTIFICATE_FOUND');

const certPath=files[0].p;
const cert=JSON.parse(fs.readFileSync(certPath,'utf8'));
const nonce=cert.nonce;
if(!nonce) throw new Error('CERTIFICATE_NONCE_MISSING');

async function json(url,opts={}){const r=await fetch(url,opts);if(!r.ok)throw new Error(`HTTP_${r.status}_${url}`);return r.json();}
const targets=await json(`${CDP}/json/list`);
const target=targets.find(t=>t.type==='page'&&/perplexity\.ai/i.test(t.url||''));
if(!target?.webSocketDebuggerUrl) throw new Error('PERPLEXITY_PAGE_NOT_FOUND');

const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('PAGE_CDP_CONNECT_TIMEOUT')),15000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('PAGE_CDP_CONNECT_ERROR'));},{once:true});});
let seq=0;const pending=new Map();
ws.addEventListener('message',ev=>{let msg;try{msg=JSON.parse(ev.data);}catch{return;}if(!msg.id||!pending.has(msg.id))return;const p=pending.get(msg.id);pending.delete(msg.id);clearTimeout(p.timer);if(msg.error)p.reject(new Error(`CDP_${msg.error.code}:${msg.error.message}`));else p.resolve(msg.result||{});});
function call(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT_${method}`));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evalJs(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(`EVAL_EXCEPTION_${r.exceptionDetails.text||'unknown'}`);return r.result?.value;}
await call('Runtime.enable');

function parse(m){return {salt:Number(m[1]),coeff:[Number(m[2]),Number(m[3]),Number(m[4])],sums:{A:Number(m[5]),B:Number(m[6]),C:Number(m[7])},terms:{A:Number(m[8]),B:Number(m[9]),C:Number(m[10])},checksum:Number(m[11])};}
function same(a,b){return JSON.stringify(a)===JSON.stringify(b);}
const re=new RegExp(`PERPLEXITY_CERT_RESULT:${nonce}:(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+):(\\d+)`,'g');

let last=null,stable=0,body='';
const started=Date.now();
while(Date.now()-started<30000){
  body=await evalJs(`String(document.body?.innerText||'')`).catch(()=> '');
  const matches=[...body.matchAll(re)];
  const current=matches.length?parse(matches[matches.length-1]):null;
  if(current&&last&&same(current,last)) stable++; else stable=0;
  last=current;
  if(current&&stable>=4) break;
  await sleep(1000);
}

if(!last){
  console.log('PERPLEXITY_STABLE_VERIFY=false');
  console.log(`NONCE=${nonce}`);
  console.log('ERROR=FINAL_RESULT_NOT_FOUND_IN_STABLE_PAGE');
  ws.close();
  process.exit(2);
}

const exp=cert.expected;
const passed=last.salt===exp.master.salt&&last.coeff[0]===exp.master.coeff[0]&&last.coeff[1]===exp.master.coeff[1]&&last.coeff[2]===exp.master.coeff[2]&&last.sums.A===exp.sums.A&&last.sums.B===exp.sums.B&&last.sums.C===exp.sums.C&&last.terms.A===exp.terms.A&&last.terms.B===exp.terms.B&&last.terms.C===exp.terms.C&&last.checksum===exp.checksum;

const previousActual=cert.actual;
cert.initial_capture=previousActual;
cert.actual=last;
cert.post_stream_verification={performed_at:new Date().toISOString(),stable_polls:stable+1,method:'re-read completed DOM without new prompt',passed};
cert.certified=passed;
fs.writeFileSync(certPath,JSON.stringify(cert,null,2));

console.log(`PERPLEXITY_STABLE_VERIFY=${passed?'true':'false'}`);
console.log(`NONCE=${nonce}`);
console.log(`INITIAL_CHECKSUM=${previousActual?.checksum ?? 'unknown'}`);
console.log(`STABLE_CHECKSUM=${last.checksum}`);
console.log(`EXPECTED_CHECKSUM=${exp.checksum}`);
console.log(`CERTIFICATE_UPDATED=${certPath}`);
if(passed) console.log('CLASSIFICATION=STREAMING_CAPTURE_RACE_CONFIRMED');
else console.log('CLASSIFICATION=MODEL_OR_RESPONSE_FAILURE_CONFIRMED');
ws.close();
if(!passed) process.exit(2);
