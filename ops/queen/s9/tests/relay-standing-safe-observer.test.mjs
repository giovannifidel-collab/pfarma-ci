import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {
 STANDING_KIND,POLICY_SHA,SOURCE_SHA,
 inspectStandingSafeEvent,processStandingSafeObservation,
 executeStandingSafeFromEnv
} from '../relay-standing-safe-observer.mjs';

const mission='6d32fd0b-5859-477c-8c89-4fdb18f89c2a';
const payload=()=>({
 kind:STANDING_KIND,
 mission_id:mission,
 source_sha:SOURCE_SHA,policy_blob_sha:POLICY_SHA,
 project_id:'hive',level:0,action:'world.observe',
 paid_fallback:false,project_writes:false,auto_merge:false,
 auto_deploy:false,can_train_school:false,no_new_provider_dispatch:true
});
const event=(patch={})=>({
 version:'1',id:'s1-test-123',type:'queen.cycle.continue',
 source:'github.repository_dispatch',occurred_at:'2026-11-18T12:00:00Z',
 correlation_id:mission,hop:0,max_hops:8,payload:payload(),...patch
});
const grant={
 allowed:true,decision:'ALLOW_STANDING_HIVE_CERTIFIED_SAFE',
 grant_id:'85294f2b-f816-4564-b3e8-5c275d0f682d',
 max_authority_level:2,
 can_write_project:false,can_deploy:false,can_pay:false,
 can_auto_merge:false,can_train_school:false
};
const world={ok:true,state:{
 world:{key:'hive.world.runtime',value:{world_version:1,snapshot:'read-only'},updated_at:'2026-11-18T12:00:00Z'},
 canonical:{constitution_version:'0.1.0'}
}};

test('standing subtype uses EXACT existing canonical S1 event, other events are untouched',()=>{
 assert.equal(inspectStandingSafeEvent(event(),SOURCE_SHA).decision,'NEEDS_PROTECTED_ACTIVE_OWNER_GRANT');
 assert.equal(inspectStandingSafeEvent(event({payload:{}}),SOURCE_SHA).handled,false);
 assert.equal(inspectStandingSafeEvent(event({payload:{kind:'queen.s9.5.verified_receipt_reconciliation'}}),SOURCE_SHA).handled,false);
 assert.equal(inspectStandingSafeEvent(event({type:'world.state.changed',payload:{kind:STANDING_KIND}}),SOURCE_SHA).handled,true);
});

test('wrong scope, source, policy, malformed claim, forbidden operation quarantine BEFORE grant',()=>{
 const rejected=[
  event({payload:{...payload(),project_id:'pfarma-cloud'}}),
  event({payload:{...payload(),level:3}}),
  event({payload:{...payload(),action:'deploy'}}),
  event({payload:{...payload(),action:'secret.rotate'}}),
  event({payload:{...payload(),source_sha:'a'.repeat(40)}}),
  event({payload:{...payload(),policy_blob_sha:'b'.repeat(40)}}),
  event({payload:{...payload(),paid_fallback:true}}),
  event({payload:{...payload(),can_train_school:true}}),
  event({payload:{...payload(),project_writes:true}}),
  event({payload:{...payload(),auto_merge:true}}),
  event({payload:{...payload(),auto_deploy:true}}),
  event({payload:{...payload(),no_new_provider_dispatch:false}}),
  event({payload:{...payload(),injected:'untrusted'}}),
  event({payload:{kind:'queen.s9.standing.fake'}}),
  event({correlation_id:'not-signed'}),
  event({hop:1}),event({max_hops:16}),
  event({source:'github.workflow_dispatch'}),
  event({type:'verification.result.ready'})
 ];
 for(const e of rejected){
  const result=inspectStandingSafeEvent(e,SOURCE_SHA);
  assert.equal(result.handled,true);
  assert.equal(result.decision,'QUARANTINE_STANDING_SAFE_DENIED');
  assert.equal(result.can_dispatch,false);
 }
 assert.equal(inspectStandingSafeEvent(event(),'a'.repeat(40)).decision,'QUARANTINE_STANDING_SAFE_DENIED');
});

test('live signed scope is verified before world observation; no dispatch or raw world logging',async()=>{
 const calls=[];
 const r=await processStandingSafeObservation({
  event:event(),sourceSha:SOURCE_SHA,
  checkGrant:async req=>{calls.push(['grant',req]);return grant;},
  observeWorld:async()=>{calls.push(['world']);return world;}
 });
 assert.deepEqual(calls.map(x=>x[0]),['grant','world']);
 assert.deepEqual(calls[0][1],{policy_blob_sha:POLICY_SHA,project_id:'hive',level:0,action:'world.observe'});
 assert.equal(r.decision,'STANDING_WORLD_OBSERVED_READ_ONLY');
 assert.match(r.world_digest,/^[a-f0-9]{64}$/);
 assert.equal(r.grant_id,grant.grant_id);
 assert.equal(r.mission_id,mission);
 for(const field of ['can_dispatch','can_retry','can_write','can_train_school','paid_fallback'])
  assert.equal(r[field],false);
 assert.equal(JSON.stringify(r).includes('snapshot'),false);
});

test('repeated pure read is idempotent; neither action dispatches any new event or provider',async()=>{
 let grantChecks=0,reads=0;
 const f=()=>processStandingSafeObservation({event:event(),sourceSha:SOURCE_SHA,
  checkGrant:async()=>{grantChecks++;return grant;},
  observeWorld:async()=>{reads++;return world;}
 });
 const a=await f(),b=await f();
 assert.equal(grantChecks,2);
 assert.equal(reads,2);
 assert.equal(a.world_digest,b.world_digest);
 assert.equal(a.can_dispatch,false);
 assert.equal(b.can_dispatch,false);
 // This is NOT durable replay CAS: repeated observation is harmless, not deduped.
});

test('revoked, expired, absent and malformed grants all fail closed before world read',async()=>{
 for(const g of [
  {decision:'DENY_NO_ACTIVE_SIGNED_GRANT',allowed:false},
  {decision:'DENY_REVOKED',allowed:false},
  {decision:'ALLOW_STANDING_HIVE_CERTIFIED_SAFE',allowed:true,can_deploy:true},
  {...grant,grant_id:'invalid'},
  null
 ]){
  let reads=0;
  const r=await processStandingSafeObservation({event:event(),sourceSha:SOURCE_SHA,
   checkGrant:async()=>g,observeWorld:async()=>{reads++;return world;}});
  assert.equal(r.handled,true);
  assert.equal(r.decision,'QUARANTINE_STANDING_SAFE_DENIED');
  assert.equal(reads,0);
 }
});

test('unavailable grant endpoint, world endpoint or corrupted snapshot blocks routing',async()=>{
 const cases=[
  {checkGrant:async()=>{throw Error('unavailable');},observeWorld:async()=>world},
  {checkGrant:async()=>grant,observeWorld:async()=>{throw Error('unavailable');}},
  {checkGrant:async()=>grant,observeWorld:async()=>({ok:true,state:{world:{}}})},
  {checkGrant:async()=>grant,observeWorld:async()=>({ok:false,state:world.state})}
 ];
 for(const c of cases){
  const r=await processStandingSafeObservation({event:event(),sourceSha:SOURCE_SHA,...c});
  assert.equal(r.decision,'QUARANTINE_STANDING_SAFE_DENIED');
 }
});

test('real env path uses only protected POST grant then GET existing state, never writes',async()=>{
 const requests=[];
 const env={
  HIVE_EVENT_JSON:JSON.stringify(event()),PRIVATE_REF:SOURCE_SHA,
  GITHUB_EVENT_NAME:'repository_dispatch',GITHUB_RUN_ATTEMPT:'1',
  HIVE_RUNTIME_BEARER_TOKEN:'mock-runtime-secret',
  CF_ACCESS_CLIENT_ID:'mock-service',
  CF_ACCESS_CLIENT_SECRET:'mock-secret'
 };
 const fetchImpl=async(url,options)=>{
  requests.push({url,method:options.method,body:options.body});
  const data=options.method==='POST'?grant:world;
  return {ok:true,json:async()=>data};
 };
 const r=await executeStandingSafeFromEnv(env,fetchImpl);
 assert.equal(r.decision,'STANDING_WORLD_OBSERVED_READ_ONLY');
 assert.deepEqual(requests.map(x=>x.method),['POST','GET']);
 assert.ok(requests[0].url.endsWith('/api/queen-standing-scope'));
 assert.ok(requests[1].url.endsWith('/api/queen-state'));
 assert.equal(requests.some(x=>/dispatches|school|provider/.test(x.url)),false);
 env.GITHUB_RUN_ATTEMPT='2';
 const bad=await executeStandingSafeFromEnv(env,async()=>{throw Error('network must not be used')});
 assert.equal(bad.decision,'QUARANTINE_STANDING_SAFE_DENIED');
});

test('existing S1 source contains one standing gate and preserves only original S1',()=>{
 const s=readFileSync('.github/workflows/queen-s1-event-ingress.yml','utf8');
 const matches=s.match(/^\s*repository_dispatch:/gm)||[];
 assert.equal(matches.length,1);
 assert.equal((s.match(/id: standing/g)||[]).length,1);
 assert.equal((s.match(/steps\.standing\.outputs\.handled != 'true'/g)||[]).length,4);
 assert.equal((s.match(/steps\.s95\.outputs\.handled != 'true'/g)||[]).length,5);
 assert.ok(s.includes('node ops/queen/s9/relay-standing-safe-observer.mjs'));
 assert.ok(s.includes('node ops/queen/s9/relay-verified-receipt-bridge.mjs'));
 assert.ok(s.includes('node queen-private/ops/queen/core/event-router.mjs'));
 assert.equal(/^\s+schedule:/m.test(s),false);
 assert.ok(s.includes('SCHEDULE_DEPENDENCY=false'));
});
