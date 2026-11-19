import test from 'node:test';
import assert from 'node:assert/strict';
import clock,{decideWorldClock,performClockTick} from '../worker.mjs';
const NOW=Date.parse('2026-11-19T21:20:00Z');
const ENV={CLOCK_ENABLED:'true',GH_WORLD_DISPATCH_TOKEN:'placeholder-for-unit-tests-only'};
const world=(age=18*60000)=>({schema_version:1,policy:'authoritative-source-first',generated_at:new Date(NOW-age).toISOString(),state_fingerprint:'f'.repeat(64),projects:{hive:{source:{available:true}}}});
const run=(age=15*60000,status='completed')=>({name:'HIVE Queen Global World Sync',status,created_at:new Date(NOW-age).toISOString()});
function mock({snapshot=world(),runs={workflow_runs:[run()]},fail=null}={}){
 const calls=[];
 async function fetchImpl(url,opts={}){
   calls.push({url:String(url),method:opts.method||'GET',body:opts.body});
   if(url.includes('/contents/hive-world-state.json'))return new Response(JSON.stringify({encoding:'base64',content:Buffer.from(JSON.stringify(snapshot)).toString('base64')}),{status:200});
   if(url.includes('/runs?per_page='))return new Response(JSON.stringify(runs),{status:200});
   if(url.includes('/dispatches')){
     if(fail==='throw')throw Error('uncertain');
     return new Response(null,{status:fail==='deny'?401:204});
   }
   throw Error('unrecognized_test_request');
 }
 return {calls,fetchImpl};
}
test('original source age, not response clock, governs freshness',()=>{
 assert.equal(decideWorldClock(world(3*60000),{workflow_runs:[]},NOW),'SKIP_WORLD_FRESH');
 assert.equal(decideWorldClock(world(),{workflow_runs:[]},NOW),'DUE_AUTHENTIC_WORLD_OBSERVATION');
 assert.equal(decideWorldClock({...world(),state_fingerprint:'bad'},{workflow_runs:[]},NOW),'DENY_INVALID_WORLD');
});
test('disabled clock and missing secret never attempt network access',async()=>{
 for(const env of [{...ENV,CLOCK_ENABLED:'false'},{CLOCK_ENABLED:'true'}]){
  const f=mock();const d=await performClockTick({env,scheduledTime:NOW,nowMs:NOW,fetchImpl:f.fetchImpl});
  assert.match(d,/^(DENY|SKIP)_/);assert.equal(f.calls.length,0);
 }
});
test('stale cron event and fresh source cannot dispatch',async()=>{
 const f=mock();assert.equal(await performClockTick({env:ENV,scheduledTime:NOW-6*60000,nowMs:NOW,fetchImpl:f.fetchImpl}),'DENY_DELAYED_OR_INVALID_CRON_TICK');
 assert.equal(f.calls.length,0);
 const g=mock({snapshot:world(2*60000)});
 assert.equal(await performClockTick({env:ENV,scheduledTime:NOW,nowMs:NOW,fetchImpl:g.fetchImpl}),'SKIP_WORLD_FRESH');
 assert.equal(g.calls.length,1);
});
test('active and recently completed runs suppress duplicate dispatch',async()=>{
 for(const x of [run(1*60000,'queued'),run(1*60000,'completed'),run(7*60000,'in_progress')]){
  const f=mock({runs:{workflow_runs:[x]}});
  const result=await performClockTick({env:ENV,scheduledTime:NOW,nowMs:NOW,fetchImpl:f.fetchImpl});
  assert.match(result,/^SKIP_WORLD_JOB_/);
  assert.equal(f.calls.filter(x=>x.method==='POST').length,0);
 }
});
test('due observation starts precisely original GitHub World Sync',async()=>{
 const f=mock();
 assert.equal(await performClockTick({env:ENV,scheduledTime:NOW,nowMs:NOW,fetchImpl:f.fetchImpl}),'DISPATCHED_EXISTING_WORLD_SYNC_ONCE');
 const posts=f.calls.filter(x=>x.method==='POST');assert.equal(posts.length,1);
 assert.match(posts[0].url,/hive-world-sync\.yml\/dispatches$/);
 assert.deepEqual(JSON.parse(posts[0].body),{ref:'main',inputs:{retry_hop:'0',clock_minute:'2026-11-19T21:20:00Z'}});
});
test('unknown delivery or refusal never causes retry',async()=>{
 for(const fail of ['throw','deny']){
  const f=mock({fail});const d=await performClockTick({env:ENV,scheduledTime:NOW,nowMs:NOW,fetchImpl:f.fetchImpl});
  assert.match(d,/^DENY_DISPATCH_/);assert.equal(f.calls.filter(x=>x.method==='POST').length,1);
 }
});
test('clock has no callable public execution API',async()=>{
 const res=await clock.fetch();assert.equal(res.status,404);
});
test('single original S1 semantic wake and sole external clock are retained',async()=>{
 const {readFileSync}=await import('node:fs');
 const wf=readFileSync('.github/workflows/hive-world-sync.yml','utf8');
 assert.equal((wf.match(/^  schedule:/gm)||[]).length,0);
 assert.ok(wf.includes('clock_minute:'));
 assert.equal((wf.match(/event_type:"world-state-changed"/g)||[]).length,1);
 assert.ok(wf.includes("if: steps.publish.outputs.changed == 'true'"));
 assert.ok(wf.includes('WORLD_OBSERVATION_HEARTBEAT=RECORDED_NO_S1_WAKE'));
 const active=readFileSync('ops/queen/s10/world-clock/wrangler.jsonc','utf8');
 const rollback=readFileSync('ops/queen/s10/world-clock/wrangler.disabled.jsonc','utf8');
 assert.match(active,/"crons": \["\* \* \* \* \*"\]/);
 assert.match(rollback,/"crons": \[\]/);
});
console.log('S10_WORLD_CLOCK_MINUTE_SOURCE_NEGATIVE_TESTS=PASS');
