import test from 'node:test';
import assert from 'node:assert/strict';
import {inspectS95Envelope,processS95Receipt,runTrustedS95IngressFromEnv,S95_KIND}
 from './relay-verified-receipt-bridge.mjs';
const mission='4dc4f64c-ede8-4cb2-a5e9-c62a966db3c8';
const payload=()=>({kind:S95_KIND,verified:true,mission_id:mission,
 exact_source_sha:'a'.repeat(40),receipt_sha256:'b'.repeat(64),
 owner_ci_run_id:43381880192,provider_ci_run_id:43383170987,
 independent_ci_run_id:43383190862,existing_event_id:1232,
 paid_fallback:false,can_train_school:false,no_new_provider_dispatch:true});
const event=()=>({version:'1',type:'verification.result.ready',source:'github.repository_dispatch',
 hop:0,max_hops:8,payload:payload()});
const gitRun=(id)=>({id,status:'completed',conclusion:'success',run_attempt:1,
 event:id===43381880192?'workflow_dispatch':'push',
 actor:{login:'giovannifidel-collab'}});
const completed=()=>({ok:true,decision:'EXISTING_RECEIPT_FINALIZED_ONCE',
 can_dispatch:false,can_retry:false,can_train_school:false,paid_fallback:false});
test('all other S1 events are unchanged; no backend call',async()=>{
 let n=0;const r=await processS95Receipt({
  event:{type:'queen.cycle.continue',payload:{self_test:true}},
  fetchRun:async()=>{n++},callProtectedCas:async()=>{n++}
 });
 assert.equal(r.handled,false);assert.equal(n,0);
});
test('zero dispatch verified result may finalize only through private Neon',async()=>{
 let n=0;
 const r=await processS95Receipt({event:event(),
  fetchRun:async id=>gitRun(id),
  callProtectedCas:async body=>{
   n++;assert.equal(body.no_new_provider_dispatch,true);
   assert.equal(body.can_train_school,false);
   assert.equal(body.existing_event_id,1232);return completed();
  }
 });
 assert.equal(n,1);assert.equal(r.decision,'EXISTING_RECEIPT_FINALIZED_ONCE');
 assert.equal(r.can_dispatch,false);assert.equal(r.can_train_school,false);
});
test('replayed verified receipt never dispatches or trains',async()=>{
 const r=await processS95Receipt({event:event(),fetchRun:async id=>gitRun(id),
 callProtectedCas:async()=>({...completed(),decision:'ALREADY_TERMINAL_NO_REDISPATCH'})});
 assert.equal(r.decision,'ALREADY_TERMINAL_NO_REDISPATCH');
});
test('missing permission, forged owner, failed provider CI prevent DB request',async()=>{
 const badRuns=[
  (id)=>({...gitRun(id),conclusion:'failure'}),
  (id)=>({...gitRun(id),actor:{login:'not-Owner'}}),
  (id)=>({...gitRun(id),run_attempt:2}),
 ];
 for(const make of badRuns){let calls=0;
  const r=await processS95Receipt({event:event(),
   fetchRun:async id=>id===43381880192?make(id):gitRun(id),
   callProtectedCas:async()=>{calls++;return completed()}
  });
  assert.equal(r.decision,'QUARANTINE_NO_PROVIDER_REDISPATCH');assert.equal(calls,0);
 }
});
test('payload verified true cannot grant authority; unknown mission never proceeds',async()=>{
 const variants=[
  {...event(),payload:{...payload(),exact_source_sha:'not a sha'}},
  {...event(),payload:{...payload(),owner_ci_run_id:43383170987}},
  {...event(),payload:{...payload(),paid_fallback:true}},
  {...event(),payload:{...payload(),can_train_school:true}},
  {...event(),payload:{...payload(),existing_event_id:0}},
  {...event(),source:'model.self_attested'},
  {...event(),hop:1},
 ];
 for(const e of variants){let n=0;
  const r=await processS95Receipt({event:e,
   fetchRun:async()=>{n++},callProtectedCas:async()=>{n++}});
  assert.equal(r.decision,'QUARANTINE_NO_PROVIDER_REDISPATCH');assert.equal(n,0);}
});
test('data API error and untrusted response fail closed before School',async()=>{
 for(const fn of [async()=>{throw Error('data unavailable')},
    async()=>({ok:true,decision:'SCHOOL_RECORD_VERIFIED',can_dispatch:false})]){
  const r=await processS95Receipt({event:event(),fetchRun:async id=>gitRun(id),callProtectedCas:fn});
  assert.equal(r.decision,'QUARANTINE_NO_PROVIDER_REDISPATCH');
  assert.equal(r.can_train_school,false);
 }
});
test('missing secrets fail before any external API calls',async()=>{
 const env={HIVE_EVENT_JSON:JSON.stringify(event())};
 const r=await runTrustedS95IngressFromEnv(env,async()=>{throw Error('SHOULD_NOT_FETCH')});
 assert.equal(r.decision,'QUARANTINE_NO_PROVIDER_REDISPATCH');
});
test('server-only fetch requests exact three GitHub CI runs then one protected endpoint',async()=>{
 const calls=[];
 const env={HIVE_EVENT_JSON:JSON.stringify(event()),GH_TOKEN:'test-only',
  HIVE_RUNTIME_BEARER_TOKEN:'runtime-only',HIVE_BASE_URL:'https://hive-alveare.pages.dev',
  CF_ACCESS_CLIENT_ID:'not-secret-test',CF_ACCESS_CLIENT_SECRET:'not-secret-test'};
 const r=await runTrustedS95IngressFromEnv(env,async(url,options)=>{
  calls.push({url,headers:options.headers,method:options.method});
  if(url.includes('/actions/runs/'))return {
    ok:true,json:async()=>gitRun(Number(url.split('/').at(-1)))
  };
  if(url.endsWith('/api/queen-s9-reconcile'))return {ok:true,json:async()=>completed()};
  throw Error('unexpected endpoint');
 });
 assert.equal(r.decision,'EXISTING_RECEIPT_FINALIZED_ONCE');
 assert.equal(calls.length,4);
 assert.equal(calls.filter(x=>x.url.endsWith('/api/queen-s9-reconcile')).length,1);
 assert.ok(calls.every(x=>!x.url.includes('/school')));
});
