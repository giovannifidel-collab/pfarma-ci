// S10 World clock: the SINGLE replacement periodic trigger, NOT an S1 event loop.
// The existing GitHub HIVE Queen Global World Sync remains the sole source writer.
// Cron runs every minute, but only asks for a real observation when due.
// No user HTTP endpoints, private project access, School, model or Neon writes.
const REPO='giovannifidel-collab/pfarma-ci';
const WORLD_URL='https://api.github.com/repos/'+REPO+'/contents/hive-world-state.json';
const RUNS_URL='https://api.github.com/repos/'+REPO+'/actions/workflows/hive-world-sync.yml/runs?per_page=12';
const DISPATCH_URL='https://api.github.com/repos/'+REPO+'/actions/workflows/hive-world-sync.yml/dispatches';
export const CLOCK_POLICY=Object.freeze({
 cron:'* * * * *',
 dueAfterMs:10*60*1000,
 minRecentRunMs:4*60*1000,
 maxScheduledLagMs:5*60*1000,
 maxFutureSourceMs:90*1000,
 repo:REPO,
 workflow:'hive-world-sync.yml'
});
const sha64=/^[a-f0-9]{64}$/;
const noCache=Object.freeze({'Cache-Control':'no-cache','Accept':'application/vnd.github+json',
 'X-GitHub-Api-Version':'2022-11-28','User-Agent':'HIVE-S10-World-Clock'});
const isoMinute=ms=>new Date(Math.floor(ms/60000)*60000).toISOString().replace('.000Z','Z');
const ms=s=>typeof s==='string'?Date.parse(s):NaN;
export function decideWorldClock(world,runs,nowMs){
 if(!world||world.schema_version!==1||world.policy!=='authoritative-source-first'||
   !sha64.test(world.state_fingerprint||'')||typeof world.projects!=='object'||!world.projects||
   Array.isArray(world.projects))return 'DENY_INVALID_WORLD';
 const published=ms(world.generated_at);
 if(!Number.isFinite(published)||published>nowMs+CLOCK_POLICY.maxFutureSourceMs)
   return 'DENY_WORLD_TIMESTAMP';
 if(nowMs-published<CLOCK_POLICY.dueAfterMs)return 'SKIP_WORLD_FRESH';
 if(!Array.isArray(runs?.workflow_runs))return 'DENY_RUNS_MISSING';
 for(const run of runs.workflow_runs){
   if(run?.name!=='HIVE Queen Global World Sync')continue;
   const started=ms(run.created_at);
   if(!Number.isFinite(started)||started>nowMs+CLOCK_POLICY.maxFutureSourceMs)continue;
   const age=nowMs-started;
   if(run.status!=='completed'&&age<60*60*1000)return 'SKIP_WORLD_JOB_ACTIVE';
   if(age<CLOCK_POLICY.minRecentRunMs)return 'SKIP_WORLD_JOB_COOLDOWN';
 }
 return 'DUE_AUTHENTIC_WORLD_OBSERVATION';
}
export async function performClockTick({env,scheduledTime,fetchImpl=fetch,nowMs=Date.now()}){
 const token=env?.GH_WORLD_DISPATCH_TOKEN;
 if(typeof token!=='string'||token.length<16)return 'DENY_CLOCK_SECRET_NOT_CONFIGURED';
 if(env?.CLOCK_ENABLED!=='true')return 'SKIP_CLOCK_NOT_ACTIVATED';
 if(!Number.isSafeInteger(scheduledTime)||Math.abs(nowMs-scheduledTime)>CLOCK_POLICY.maxScheduledLagMs)
   return 'DENY_DELAYED_OR_INVALID_CRON_TICK';
 const headers={...noCache,Authorization:'Bearer '+token};
 let world;
 try{
   const response=await fetchImpl(WORLD_URL,{headers,redirect:'error'});
   if(!response.ok)return 'DENY_GITHUB_WORLD_SOURCE_HTTP';
   const v=await response.json();
   if(typeof v?.content!=='string'||v.encoding!=='base64')return 'DENY_WORLD_BLOB_FORMAT';
   world=JSON.parse(atob(v.content.replace(/\s/g,'')));
 }catch{return 'DENY_WORLD_READ_OR_PARSE_ERROR';}
 const sourceMs=ms(world.generated_at);
 if(!Number.isFinite(sourceMs)||sourceMs>nowMs+CLOCK_POLICY.maxFutureSourceMs)
   return 'DENY_WORLD_TIMESTAMP';
 if(nowMs-sourceMs<CLOCK_POLICY.dueAfterMs)return 'SKIP_WORLD_FRESH';
 let runs;
 try{
   const response=await fetchImpl(RUNS_URL,{headers,redirect:'error'});
   if(!response.ok)return 'DENY_GITHUB_WORKFLOW_RUNS_HTTP';
   runs=await response.json();
 }catch{return 'DENY_WORKFLOW_RUNS_READ_ERROR';}
 const decision=decideWorldClock(world,runs,nowMs);
 if(decision!=='DUE_AUTHENTIC_WORLD_OBSERVATION')return decision;
 const payload={
   ref:'main',
   inputs:{retry_hop:'0',clock_minute:isoMinute(scheduledTime)}
 };
 try{
   const response=await fetchImpl(DISPATCH_URL,{
     method:'POST',
     headers:{...headers,'Content-Type':'application/json'},
     redirect:'error',
     body:JSON.stringify(payload)
   });
   if(response.status!==204)return 'DENY_DISPATCH_RESPONSE_UNCERTAIN_NO_RETRY';
   return 'DISPATCHED_EXISTING_WORLD_SYNC_ONCE';
 }catch{
   // Delivery might have occurred; NEVER blindly retry within this invocation.
   return 'DENY_DISPATCH_OUTCOME_UNKNOWN_NO_RETRY';
 }
}
export default {
 async scheduled(controller,env,ctx){
   const execute=async()=>{
     const result=await performClockTick({env,scheduledTime:controller.scheduledTime});
     console.log('S10_WORLD_CLOCK_DECISION='+result);
   };
   ctx.waitUntil(execute());
 },
 async fetch(){
   return new Response('Not Found',{status:404,headers:{'Cache-Control':'no-store'}});
 }
};
