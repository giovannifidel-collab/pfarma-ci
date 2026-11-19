// Deterministic, source-only decision for the EXISTING Queen World Sync publication.
// Publishing an unchanged observation clock must NEVER generate a semantic S1 wake.
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';

const sha64=/^[0-9a-f]{64}$/i;
const epoch=v=>{
  if(typeof v!=='string'||!v.endsWith('Z'))return NaN;
  return Date.parse(v);
};

export function decideWorldSnapshotPublication(previous, next, {
  nowMs=Date.now(),minObservationMs=10*60*1000,maxSourceFutureMs=90*1000
}={}){
  const deny=(reason)=>({status:'DENY',reason,semantic_changed:false,observation_recorded:false});
  if(!next||typeof next!=='object'||Array.isArray(next)||
    next.schema_version!==1||next.policy!=='authoritative-source-first'||
    !sha64.test(next.state_fingerprint||'')||!next.projects||typeof next.projects!=='object'||
    Array.isArray(next.projects))
    return deny('invalid_authoritative_world_envelope');
  const nextMs=epoch(next.generated_at);
  if(!Number.isFinite(nextMs)||nextMs>nowMs+maxSourceFutureMs||nextMs<nowMs-5*60*1000)
    return deny('source_observation_clock_not_fresh');
  if(!previous||!sha64.test(previous.state_fingerprint||'')){
    return {status:'SEMANTIC',reason:'first_canonical_world_observation',
      semantic_changed:true,observation_recorded:true};
  }
  if(previous.schema_version!==1||previous.policy!=='authoritative-source-first')
    return deny('previous_world_envelope_not_trusted');
  const oldMs=epoch(previous.generated_at);
  if(!Number.isFinite(oldMs)||oldMs>nowMs+maxSourceFutureMs)
    return deny('previous_world_clock_missing_or_future');
  if(nextMs<=oldMs)
    return deny('out_of_order_or_replayed_world_observation');
  if(previous.state_fingerprint!==next.state_fingerprint)
    return {status:'SEMANTIC',reason:'fingerprint_changed',
      semantic_changed:true,observation_recorded:true};
  if(nextMs-oldMs<minObservationMs)
    return {status:'SKIP',reason:'fresh_observation_already_published',
      semantic_changed:false,observation_recorded:false};
  return {status:'HEARTBEAT',reason:'same_semantics_new_authoritative_observation',
    semantic_changed:false,observation_recorded:true};
}

if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{
    const oldFile=process.argv[2],newFile=process.argv[3];
    if(!oldFile||!newFile)throw Error('missing_observation_source_files');
    const previous=JSON.parse(readFileSync(oldFile,'utf8'));
    const next=JSON.parse(readFileSync(newFile,'utf8'));
    const decision=decideWorldSnapshotPublication(previous,next);
    if(decision.status==='DENY'){
      console.error('WORLD_OBSERVATION_FAIL_CLOSED_REASON='+decision.reason);
      process.exitCode=35;
    }else{
      console.log(decision.status);
    }
  }catch{
    console.error('WORLD_OBSERVATION_SOURCE_UNREADABLE_FAIL_CLOSED');
    process.exitCode=36;
  }
}
