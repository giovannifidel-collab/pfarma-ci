import test from 'node:test';
import assert from 'node:assert/strict';
import clock,{performClockTick,CLOCK_POLICY} from '../worker.mjs';
const NOW=Date.parse('2026-11-20T15:16:37Z');
const ENV={CLOCK_ENABLED:'true',CF_ACCESS_CLIENT_ID:'test-client-identifier.access',CF_ACCESS_CLIENT_SECRET:'test-secret-placeholder-value-123456'};
const BROKER='https://hive-alveare.pages.dev/api/s10-world-clock-dispatch';
function mock({status=202,ok=true,decision='DISPATCHED_ORIGINAL_WORLD_SYNC',error=null,mime='application/json',failure=null}={}){
 const calls=[];
 const fetchImpl=async(url,opts={})=>{
   calls.push({url:String(url),method:opts.method||'GET',body:opts.body,headers:opts.headers,redirect:opts.redirect});
   if(failure==='throw')throw Error('unknown delivery outcome');
   assert.equal(String(url),BROKER,'Worker must never contact GitHub directly');
   return new Response(mime==='application/json'?JSON.stringify({ok,decision,error}):'<html>Access denied</html>',{status:failure==='http403'?403:status,headers:{'content-type':mime}});
 };
 return {calls,fetchImpl};
}
async function tick(f,env=ENV,scheduledTime=NOW){return performClockTick({env,scheduledTime,nowMs:NOW,fetchImpl:f.fetchImpl})}
test('exact minute schedule and no implicit paid provider',()=>{
 assert.equal(CLOCK_POLICY.cron,'* * * * *');
 assert.equal(CLOCK_POLICY.workflow,'hive-world-sync.yml');
 assert.equal(CLOCK_POLICY.repo,'giovannifidel-collab/pfarma-ci');
});
test('disabled Worker, absent or partial Access credentials, delayed/future cron are fail-closed with zero egress',async()=>{
 for(const [env,time] of [
  [{...ENV,CLOCK_ENABLED:'false'},NOW],
  [{...ENV,CF_ACCESS_CLIENT_ID:''},NOW],
  [{...ENV,CF_ACCESS_CLIENT_SECRET:''},NOW],
  [ENV,NOW-360001],
  [ENV,NOW+360001]
 ]){
  const f=mock();const result=await tick(f,env,time);
  assert.match(result,/^(DENY|SKIP)_/);
  assert.equal(f.calls.length,0);
 }
});
test('Worker sends exactly one bounded Access-authenticated POST; Pages alone authorizes World source and queue',async()=>{
 const f=mock();
 assert.equal(await tick(f),'DISPATCHED_EXISTING_WORLD_SYNC_ONCE_VIA_PAGES');
 assert.equal(f.calls.length,1);
 assert.equal(f.calls[0].url,BROKER);
 assert.equal(f.calls[0].method,'POST');
 assert.equal(f.calls[0].redirect,'error');
 assert.deepEqual(JSON.parse(f.calls[0].body),{clock_minute:'2026-11-20T15:16:00Z'});
 assert.equal(f.calls[0].headers['CF-Access-Client-Id'],ENV.CF_ACCESS_CLIENT_ID);
 assert.equal(f.calls[0].headers['CF-Access-Client-Secret'],ENV.CF_ACCESS_CLIENT_SECRET);
 assert.ok(!JSON.stringify(f.calls).includes('api.github.com'));
 assert.ok(!JSON.stringify(f.calls).includes('raw.githubusercontent.com'));
});
test('broker-authenticated real World freshness, active job and cooldown all remain skip, never treated as dispatch',async()=>{
 for(const decision of ['SKIP_FRESH','SKIP_ACTIVE','SKIP_COOLDOWN']){
   const f=mock({status:200,ok:true,decision});
   assert.equal(await tick(f),'SKIP_AUTHENTIC_WORLD_'+decision+'_VIA_PAGES');
   assert.equal(f.calls.length,1);
 }
});
test('broker 200 with unknown, forged, or failed status is denied, never retried',async()=>{
 for(const args of [
 {status:200,ok:true,decision:'DUE_ORIGINAL_WORLD_SYNC'},
 {status:200,ok:false,decision:'SKIP_FRESH'},
 {status:200,ok:true,decision:'DISPATCHED_ORIGINAL_WORLD_SYNC'},
 {status:403,ok:false,decision:'ACCESS_SERVICE_SIGNATURE_DENY'},
 {status:503,ok:false,decision:'DENY_WORLD_TIME'},
 {status:202,ok:false,decision:'DISPATCHED_ORIGINAL_WORLD_SYNC'},
 {status:202,ok:true,decision:'OTHER_DISPATCH'}
 ]){
  const f=mock(args),result=await tick(f);
  assert.match(result,/^DENY_/);
  assert.equal(f.calls.length,1);
 }
});
test('broker HTTP status and allowlisted error code are auditable without exposing arbitrary bodies',async()=>{
 for(const [status,error,expected] of [
  [403,'ACCESS_SERVICE_SIGNATURE_DENY','DENY_PAGES_BROKER_HTTP_403_ACCESS_SERVICE_SIGNATURE_DENY_NO_RETRY'],
  [503,'WORLD_SOURCE_DENY','DENY_PAGES_BROKER_HTTP_503_WORLD_SOURCE_DENY_NO_RETRY'],
  [503,'RUNS_READ_DENY','DENY_PAGES_BROKER_HTTP_503_RUNS_READ_DENY_NO_RETRY'],
  [502,'GITHUB_DISPATCH_DENY','DENY_PAGES_BROKER_HTTP_502_GITHUB_DISPATCH_DENY_NO_RETRY'],
  [409,'CLOCK_REPLAY_OR_FUTURE_DENY','DENY_PAGES_BROKER_HTTP_409_CLOCK_REPLAY_OR_FUTURE_DENY_NO_RETRY'],
  [403,'potential-secret-in-error','DENY_PAGES_BROKER_HTTP_403_OPAQUE_NO_RETRY']
 ]){
  const f=mock({status,ok:false,error});
  assert.equal(await tick(f),expected);
  assert.equal(f.calls.length,1);
 }
 const html=mock({status:403,mime:'text/html'});
 assert.equal(await tick(html),'DENY_PAGES_BROKER_HTTP_403_OPAQUE_NO_RETRY');
 assert.equal(html.calls.length,1);
});
test('unknown delivery/outage cannot trigger a second request on same tick',async()=>{
 const f=mock({failure:'throw'});
 assert.equal(await tick(f),'DENY_DISPATCH_OUTCOME_UNKNOWN_NO_RETRY');
 assert.equal(f.calls.length,1);
});
test('scheduled hook records only the broker decision; fetch HTTP endpoint is not exposed',async()=>{
 const f=mock({status:200,ok:true,decision:'SKIP_FRESH'});
 let wait;
 const oldFetch=globalThis.fetch;
 try{
   globalThis.fetch=f.fetchImpl;
   await clock.scheduled({scheduledTime:Date.now()},ENV,{waitUntil:p=>{wait=p;}});
   await wait;
 }finally{globalThis.fetch=oldFetch}
 assert.equal(f.calls.length,1);
 const res=await clock.fetch();
 assert.equal(res.status,404);
});
test('single original S1, semantic-only wake, sole Cloudflare minute trigger and bounded rollback',async()=>{
 const {readFileSync}=await import('node:fs');
 const wf=readFileSync('.github/workflows/hive-world-sync.yml','utf8');
 assert.equal((wf.match(/^  schedule:/gm)||[]).length,0);
 assert.equal((wf.match(/^  repository_dispatch:/gm)||[]).length,1);
 assert.ok(wf.includes('types: [hive_world_clock_tick]'));
 assert.equal((wf.match(/event_type:"world-state-changed"/g)||[]).length,1);
 assert.ok(wf.includes("if: steps.publish.outputs.changed == 'true'"));
 assert.ok(wf.includes('WORLD_OBSERVATION_HEARTBEAT=RECORDED_NO_S1_WAKE'));
 const active=readFileSync('ops/queen/s10/world-clock/wrangler.jsonc','utf8');
 const rollback=readFileSync('ops/queen/s10/world-clock/wrangler.disabled.jsonc','utf8');
 assert.match(active,/"crons": \["\* \* \* \* \*"\]/);
 assert.match(rollback,/"crons": \[\]/);
 assert.match(rollback,/"CLOCK_ENABLED": "false"/);
 const worker=readFileSync('ops/queen/s10/world-clock/worker.mjs','utf8');
 assert.ok(!worker.includes('raw.githubusercontent.com'));
 assert.ok(!worker.includes('api.github.com'));
 assert.equal((worker.match(/method:'POST'/g)||[]).length,1);
});
console.log('S10_WORLD_CLOCK_PAGES_SINGLE_ARBITER_NEGATIVE_TESTS=PASS');
