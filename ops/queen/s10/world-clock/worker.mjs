// S10 World clock: the SINGLE replacement periodic trigger, NOT an S1 event loop.
// The existing GitHub HIVE Queen Global World Sync remains the sole source writer.
// Cron runs every minute, but only asks for a real observation when due.
// No user HTTP endpoints, private project access, School, model or Neon writes.
const REPO='giovannifidel-collab/pfarma-ci';
const WORLD_URL='https://raw.githubusercontent.com/'+REPO+'/main/hive-world-state.json';
const RUNS_URL='https://api.github.com/repos/'+REPO+'/actions/workflows/hive-world-sync.yml/runs?per_page=12';
const DISPATCH_URL='https://hive-alveare.pages.dev/api/s10-world-clock-dispatch';
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
 'X-GitHub-Api-Version':'2022-11-28','User-Agent':'HIVE-S10-World-Clock/1.0'});
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
 const clientId=env?.CF_ACCESS_CLIENT_ID,clientSecret=env?.CF_ACCESS_CLIENT_SECRET;
 if(typeof clientId!=='string'||clientId.length<16||typeof clientSecret!=='string'||clientSecret.length<20)return 'DENY_EXISTING_ACCESS_SERVICE_SECRET_NOT_CONFIGURED';
 if(env?.CLOCK_ENABLED!=='true')return 'SKIP_CLOCK_NOT_ACTIVATED';
 if(!Number.isSafeInteger(scheduledTime)||Math.abs(nowMs-scheduledTime)>CLOCK_POLICY.maxScheduledLagMs)
   return 'DENY_DELAYED_OR_INVALID_CRON_TICK';
 const headers={...noCache};
 let world;
 try{
   const response=await fetchImpl(WORLD_URL,{headers,redirect:'error'});
   if(!response.ok)return 'DENY_GITHUB_WORLD_SOURCE_HTTP';
   world=await response.json();
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
 const payload={clock_minute:isoMinute(scheduledTime)};
 try{
   const response=await fetchImpl(DISPATCH_URL,{
     method:'POST',
     headers:{...headers,'Content-Type':'application/json','CF-Access-Client-Id':clientId,'CF-Access-Client-Secret':clientSecret},
     redirect:'error',
     body:JSON.stringify(payload)
   });
   if(response.status!==202)return 'DENY_PAGES_BROKER_DISPATCH_RESPONSE_NO_RETRY';
   const proof=await response.json();
   if(proof?.ok!==true||proof?.decision!=='DISPATCHED_ORIGINAL_WORLD_SYNC')return 'DENY_PAGES_BROKER_RESPONSE_UNVERIFIED';
   return 'DISPATCHED_EXISTING_WORLD_SYNC_ONCE_VIA_PAGES';
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
