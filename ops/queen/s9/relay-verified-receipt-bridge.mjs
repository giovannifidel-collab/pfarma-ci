// S9.5 verified-result bridge used by the EXISTING S1 Event Ingress.
// Never creates another dispatcher; rejects unknown outcomes and prevents
// School training for verified-receipt reconciliation subtype.
export const S95_KIND='queen.s9.5.verified_receipt_reconciliation';
const SHA=/^[a-f0-9]{40}$/;
const HASH=/^[a-f0-9]{64}$/;
const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[1-8][a-f0-9]{3}-[89ab][a-f0-9]{3}-[0-9a-f]{12}$/i;
const posint=x=>Number.isSafeInteger(x)&&x>0;
const own=(x,k)=>Object.prototype.hasOwnProperty.call(x??{},k);
const deny=(reason)=>Object.freeze({handled:true,decision:'QUARANTINE_NO_PROVIDER_REDISPATCH',
 reason,can_dispatch:false,can_retry:false,can_train_school:false,paid_fallback:false});
export function inspectS95Envelope(evt){
 if(evt?.payload?.kind!==S95_KIND)return Object.freeze({handled:false,decision:'CANONICAL_S1_PASSTHROUGH'});
 if(evt?.version!=='1'||evt?.type!=='verification.result.ready'||
   evt?.source!=='github.repository_dispatch'||evt?.hop!==0||evt?.max_hops!==8||
   evt?.payload?.verified!==true||
   !UUID.test(evt.payload.mission_id||'')||
   !SHA.test(evt.payload.exact_source_sha||'')||
   !HASH.test(evt.payload.receipt_sha256||'')||
   !posint(evt.payload.owner_ci_run_id)||
   !posint(evt.payload.provider_ci_run_id)||
   !posint(evt.payload.independent_ci_run_id)||
   !posint(evt.payload.existing_event_id)||
   evt.payload.owner_ci_run_id===evt.payload.provider_ci_run_id||
   evt.payload.provider_ci_run_id===evt.payload.independent_ci_run_id||
   evt.payload.independent_ci_run_id===evt.payload.owner_ci_run_id||
   evt.payload.paid_fallback!==false||
   evt.payload.can_train_school!==false||
   evt.payload.no_new_provider_dispatch!==true)
   return deny('invalid_S9_5_receipt_envelope');
 return Object.freeze({handled:true,decision:'NEEDS_LIVE_OWNER_GH_AND_PRIVATE_NEON_CAS',payload:evt.payload});
}
const verifiedRun=(d,id)=>{
 return d&&d.id===id&&d.status==='completed'&&d.conclusion==='success'&&d.run_attempt===1;
};
export async function processS95Receipt({
 event,fetchRun,callProtectedCas
}={}){
 const c=inspectS95Envelope(event);
 if(!c.handled)return c;
 if(c.decision!=='NEEDS_LIVE_OWNER_GH_AND_PRIVATE_NEON_CAS')return c;
 if(typeof fetchRun!=='function'||typeof callProtectedCas!=='function')
  return deny('trusted_backends_unavailable');
 const p=c.payload;
 let owner,provider,independent;
 try{
  [owner,provider,independent]=await Promise.all([
   fetchRun(p.owner_ci_run_id),fetchRun(p.provider_ci_run_id),fetchRun(p.independent_ci_run_id)
  ]);
 }catch{return deny('github_independent_run_readback_unavailable')}
 if(!verifiedRun(owner,p.owner_ci_run_id)||owner.event!=='workflow_dispatch'||
  owner.actor?.login!=='giovannifidel-collab'||
  !verifiedRun(provider,p.provider_ci_run_id)||
  !verifiedRun(independent,p.independent_ci_run_id))
   return deny('owner_provider_or_independent_github_ci_not_passed');
 let response;
 try{
  response=await callProtectedCas({
   mission_id:p.mission_id,source_sha:p.exact_source_sha,
   provider_ci_run_id:p.provider_ci_run_id,
   independent_ci_run_id:p.independent_ci_run_id,
   receipt_sha256:p.receipt_sha256,existing_event_id:p.existing_event_id,
   no_new_provider_dispatch:true,can_train_school:false,paid_fallback:false
  });
 }catch{return deny('protected_neon_one_shot_cas_unavailable')}
 if(response?.ok===true &&
   ['EXISTING_RECEIPT_FINALIZED_ONCE','ALREADY_TERMINAL_NO_REDISPATCH'].includes(response.decision) &&
   response.can_dispatch===false&&response.can_retry===false&&response.can_train_school===false&&
   response.paid_fallback===false)
   return Object.freeze({handled:true,decision:response.decision,
    can_dispatch:false,can_retry:false,can_train_school:false,paid_fallback:false});
 return deny('signed_owner_private_neon_cas_denied');
}
export async function runTrustedS95IngressFromEnv(
 env=process.env,fetchImpl=fetch
){
 const event=JSON.parse(env.HIVE_EVENT_JSON||'{}');
 const check=inspectS95Envelope(event);
 if(!check.handled)return check;
 if(check.decision!=='NEEDS_LIVE_OWNER_GH_AND_PRIVATE_NEON_CAS')return check;
 if(!env.GH_TOKEN||!env.HIVE_RUNTIME_BEARER_TOKEN||
   !env.CF_ACCESS_CLIENT_ID||!env.CF_ACCESS_CLIENT_SECRET||
   !env.HIVE_BASE_URL)
   return deny('trusted_relay_credentials_not_configured');
 const gh=async(id)=>{
  const r=await fetchImpl('https://api.github.com/repos/giovannifidel-collab/pfarma-ci/actions/runs/'+id,{
   headers:{Authorization:'Bearer '+env.GH_TOKEN,Accept:'application/vnd.github+json'},
   signal:AbortSignal.timeout(20000)
  });
  if(!r.ok)throw Error('github_run_not_available');
  return r.json();
 };
 const post=async(body)=>{
  const res=await fetchImpl(env.HIVE_BASE_URL.replace(/\/$/,'')+'/api/queen-s9-reconcile',{
   method:'POST',headers:{Authorization:'Bearer '+env.HIVE_RUNTIME_BEARER_TOKEN,
    'Cf-Access-Client-Id':env.CF_ACCESS_CLIENT_ID,
    'Cf-Access-Client-Secret':env.CF_ACCESS_CLIENT_SECRET,
    'Content-Type':'application/json',Accept:'application/json'},
   body:JSON.stringify(body),signal:AbortSignal.timeout(30000)
  });
  if(!res.ok)throw Error('trusted_neon_cas_http_denied');
  return res.json();
 };
 return processS95Receipt({event,fetchRun:gh,callProtectedCas:post});
}
if(import.meta.url==='file://'+process.argv[1]){
 try{
  const r=await runTrustedS95IngressFromEnv();
  const g=process.env.GITHUB_OUTPUT;
  if(g){
   const fs=await import('node:fs');
   fs.appendFileSync(g,'handled='+(r.handled?'true':'false')+'\n');
   fs.appendFileSync(g,'decision='+r.decision+'\n');
  }
  console.log('S9_5_EXISTING_S1_INGRESS_DECISION='+r.decision);
  if(r.handled && !['EXISTING_RECEIPT_FINALIZED_ONCE','ALREADY_TERMINAL_NO_REDISPATCH'].includes(r.decision))
   process.exitCode=46;
 }catch(e){
  console.error('S9_5_FAIL_CLOSED_RECEIPT_QUARANTINE');
  process.exitCode=47;
 }
}
