// One SAFE read-only standing Owner HIVE observation, routed by EXISTING canonical S1.
// No new scheduler, dispatcher, write, School training, provider, or paid fallback.
import {createHash} from 'node:crypto';
import {appendFileSync} from 'node:fs';

export const STANDING_KIND='queen.s9.standing.safe_observation.v1';
export const POLICY_SHA='90f4fb35b8610f7738c79af0019cf1cb2582f746';
// Source authority is resolved by the EXISTING canonical S1's exact
// HIVE main SHA === relay source-pointer check. Do not freeze this at an old
// release, or safe signed observations become incorrectly unusable after
// every properly Owner-approved HIVE source merge.
const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[1-8][a-f0-9]{3}-[89ab][a-f0-9]{3}-[0-9a-f]{12}$/i;
const SRC=/^[a-f0-9]{40}$/;
const deny=reason=>Object.freeze({handled:true,decision:'QUARANTINE_STANDING_SAFE_DENIED',reason,
  can_dispatch:false,can_retry:false,can_write:false,can_train_school:false,paid_fallback:false});
const has=(o,k)=>Object.prototype.hasOwnProperty.call(o??{},k);
export function inspectStandingSafeEvent(evt,sourceSha){
  const kind=evt?.payload?.kind;
  if(typeof kind!=='string'||!kind.startsWith('queen.s9.standing.'))
    return Object.freeze({handled:false,decision:'CANONICAL_S1_PASSTHROUGH'});
  const p=evt.payload;
  if(kind!==STANDING_KIND ||
     evt.version!=='1'||evt.type!=='queen.cycle.continue'||
     evt.source!=='github.repository_dispatch'||
     evt.hop!==0||evt.max_hops!==8||
     !UUID.test(evt.correlation_id||'')||!UUID.test(p.mission_id||'')||
     evt.correlation_id!==p.mission_id||
     p.action!=='world.observe'||p.project_id!=='hive'||p.level!==0||
     p.policy_blob_sha!==POLICY_SHA||
     !SRC.test(p.source_sha||'')||!SRC.test(sourceSha||'')||
     p.source_sha!==sourceSha||
     p.paid_fallback!==false||p.project_writes!==false||
     p.auto_merge!==false||p.auto_deploy!==false||
     p.can_train_school!==false||p.no_new_provider_dispatch!==true||
     Object.keys(p).sort().join(',')!==[
       'action','auto_deploy','auto_merge','can_train_school','kind',
       'level','mission_id','no_new_provider_dispatch',
       'paid_fallback','policy_blob_sha','project_id','project_writes','source_sha'
     ].sort().join(','))
    return deny('invalid_exact_standing_hive_safe_envelope');
  return Object.freeze({handled:true,decision:'NEEDS_PROTECTED_ACTIVE_OWNER_GRANT',payload:p});
}

function allowedGrant(grant){
 return grant?.allowed===true &&
 grant?.decision==='ALLOW_STANDING_HIVE_CERTIFIED_SAFE'&&
 UUID.test(grant?.grant_id||'')&&Number.isInteger(grant?.max_authority_level)&&
 grant.max_authority_level>=0 && grant.max_authority_level<=2 &&
 grant.can_write_project===false&&grant.can_deploy===false&&
 grant.can_pay===false&&grant.can_auto_merge===false&&
 grant.can_train_school===false;
}

export async function processStandingSafeObservation({
 event,sourceSha,checkGrant,observeWorld
}={}){
 const gate=inspectStandingSafeEvent(event,sourceSha);
 if(!gate.handled||gate.decision!=='NEEDS_PROTECTED_ACTIVE_OWNER_GRANT')return gate;
 if(typeof checkGrant!=='function'||typeof observeWorld!=='function')
   return deny('trusted_signed_grant_or_observer_unavailable');
 let grant;
 try{grant=await checkGrant({
   policy_blob_sha:POLICY_SHA,project_id:'hive',level:0,action:'world.observe'
 });}catch{return deny('standing_grant_unavailable')}
 if(!allowedGrant(grant))return deny('active_standing_owner_grant_denied');
 let snapshot;
 try{snapshot=await observeWorld();}catch{return deny('world_observation_unavailable')}
 if(!snapshot||snapshot.ok!==true||!snapshot.state||
   typeof snapshot.state!=='object'||Array.isArray(snapshot.state)||
   !has(snapshot.state,'world')||
   !snapshot.state.canonical||typeof snapshot.state.canonical!=='object')
   return deny('canonical_world_snapshot_unavailable');
 // No raw private world data in CI logs; digest only verifies a real read.
 const world=snapshot.state.world;
 const digest=createHash('sha256').update(JSON.stringify({
   world,canonical:snapshot.state.canonical
 })).digest('hex');
 return Object.freeze({
   handled:true,decision:'STANDING_WORLD_OBSERVED_READ_ONLY',
   mission_id:event.correlation_id,world_digest:digest,grant_id:grant.grant_id,
   can_dispatch:false,can_retry:false,can_write:false,
   can_train_school:false,paid_fallback:false
 });
}

export async function executeStandingSafeFromEnv(env=process.env,fetchImpl=fetch){
 let event;
 try{event=JSON.parse(env.HIVE_EVENT_JSON||'{}')}
 catch{return deny('untrusted_event_json')}
 const first=inspectStandingSafeEvent(event,env.PRIVATE_REF);
 if(!first.handled||first.decision!=='NEEDS_PROTECTED_ACTIVE_OWNER_GRANT')
   return first;
 if(env.GITHUB_EVENT_NAME!=='repository_dispatch'||Number(env.GITHUB_RUN_ATTEMPT)!==1)
   return deny('non_original_single_s1_dispatch');
 if(env.HIVE_BASE_URL&&env.HIVE_BASE_URL.replace(/\/$/,'')!=='https://hive-alveare.pages.dev')
   return deny('noncanonical_cloudflare_destination_denied');
 if(!env.CF_ACCESS_CLIENT_ID||!env.CF_ACCESS_CLIENT_SECRET||
   !env.HIVE_RUNTIME_BEARER_TOKEN)return deny('trusted_relay_credentials_unavailable');
 const base='https://hive-alveare.pages.dev';
 const headers={
   Authorization:'Bearer '+env.HIVE_RUNTIME_BEARER_TOKEN,
   'Cf-Access-Client-Id':env.CF_ACCESS_CLIENT_ID,
   'Cf-Access-Client-Secret':env.CF_ACCESS_CLIENT_SECRET,
   Accept:'application/json',
   'Content-Type':'application/json'
 };
 const rpc=async(payload)=>{
   const r=await fetchImpl(base+'/api/queen-standing-scope',{
     method:'POST',headers,body:JSON.stringify(payload),
     signal:AbortSignal.timeout(20000)
   });
   if(!r.ok)throw Error('standing_owner_grant_http_deny');
   return r.json();
 };
 const observation=async()=>{
   const r=await fetchImpl(base+'/api/queen-state',{
     method:'GET',headers,signal:AbortSignal.timeout(20000)
   });
   if(!r.ok)throw Error('canonical_world_read_http_deny');
   return r.json();
 };
 return processStandingSafeObservation({
   event,sourceSha:env.PRIVATE_REF,checkGrant:rpc,observeWorld:observation
 });
}

if(import.meta.url==='file://'+process.argv[1]){
 try{
   const r=await executeStandingSafeFromEnv();
   if(process.env.GITHUB_OUTPUT){
     appendFileSync(process.env.GITHUB_OUTPUT,'handled='+(r.handled?'true':'false')+'\n');
     appendFileSync(process.env.GITHUB_OUTPUT,'decision='+r.decision+'\n');
   }
   console.log('STANDING_CANONICAL_S1_DECISION='+r.decision);
   if(r.decision==='STANDING_WORLD_OBSERVED_READ_ONLY'){
     console.log('STANDING_CANONICAL_WORLD_SHA256='+r.world_digest);
     console.log('STANDING_MISSION_ID='+r.mission_id);
     console.log('STANDING_ACTIVE_GRANT_ID='+r.grant_id);
     console.log('STANDING_NO_DURABLE_ACTION_NO_NEXT_DISPATCH_NO_SCHOOL=TRUE');
   }
   if(r.handled&&r.decision!=='STANDING_WORLD_OBSERVED_READ_ONLY')
     process.exitCode=48;
 }catch{
   console.error('STANDING_FAIL_CLOSED_NO_ROUTE_NO_PROVIDER');
   process.exitCode=49;
 }
}
