// S10 World clock: the SINGLE replacement periodic trigger, NOT an S1 event loop.
// The existing GitHub HIVE Queen Global World Sync remains the sole source writer.
// Cron runs every minute; existing authenticated Pages broker dispatches only when World is due.
// No user HTTP endpoints, private project access, School, model or Neon writes.
const REPO='giovannifidel-collab/pfarma-ci';
const DISPATCH_URL='https://hive-alveare.pages.dev/api/s10-world-clock-dispatch';
export const CLOCK_POLICY=Object.freeze({
 cron:'* * * * *',
 maxScheduledLagMs:5*60*1000,
 repo:REPO,
 workflow:'hive-world-sync.yml'
});
const noCache=Object.freeze({'Cache-Control':'no-cache','Accept':'application/vnd.github+json',
 'X-GitHub-Api-Version':'2022-11-28','User-Agent':'HIVE-S10-World-Clock/1.0'});
const isoMinute=ms=>new Date(Math.floor(ms/60000)*60000).toISOString().replace('.000Z','Z');
export async function performClockTick({env,scheduledTime,fetchImpl=fetch,nowMs=Date.now()}){
 const clientId=env?.CF_ACCESS_CLIENT_ID,clientSecret=env?.CF_ACCESS_CLIENT_SECRET;
 if(typeof clientId!=='string'||clientId.length<16||typeof clientSecret!=='string'||clientSecret.length<20)return 'DENY_EXISTING_ACCESS_SERVICE_SECRET_NOT_CONFIGURED';
 if(env?.CLOCK_ENABLED!=='true')return 'SKIP_CLOCK_NOT_ACTIVATED';
 if(!Number.isSafeInteger(scheduledTime)||Math.abs(nowMs-scheduledTime)>CLOCK_POLICY.maxScheduledLagMs)
   return 'DENY_DELAYED_OR_INVALID_CRON_TICK';
 // Cloudflare Worker cron only transports the bounded signed tick.
 // The existing Pages broker ALONE verifies authoritative GitHub World JSON,
 // original World queue/cooldown and dispatch using its existing Pages-bound token.
 // Raw GitHub reads from this Worker failed in LIVE #44759568845:
 // S10_WORLD_CLOCK_DECISION=DENY_WORLD_READ_OR_PARSE_ERROR.
 // Zero direct Github subrequests here means no second independent arbiter and
 // no unauthenticated shared Cloudflare-IP GitHub rate-limit/redirect dependency.
 const payload={clock_minute:isoMinute(scheduledTime)};
 try{
   const response=await fetchImpl(DISPATCH_URL,{
     method:'POST',redirect:'error',
     headers:{...noCache,'Content-Type':'application/json',
       'CF-Access-Client-Id':clientId,'CF-Access-Client-Secret':clientSecret},
     body:JSON.stringify(payload)
   });
   // ALL authoritative World and running-job decisions remain in Pages broker.
   // No broker-denied clock ever dispatches, and no opaque response authorizes.
   if(response.status===200){
     const result=await response.json();
     if(result?.ok===true&&['SKIP_FRESH','SKIP_ACTIVE','SKIP_COOLDOWN'].includes(result.decision))
       return 'SKIP_AUTHENTIC_WORLD_'+result.decision+'_VIA_PAGES';
     return 'DENY_PAGES_BROKER_UNVERIFIED_SKIP';
   }
   if(response.status!==202)return 'DENY_PAGES_BROKER_DISPATCH_RESPONSE_NO_RETRY';
   const proof=await response.json();
   if(proof?.ok!==true||proof?.decision!=='DISPATCHED_ORIGINAL_WORLD_SYNC')
     return 'DENY_PAGES_BROKER_RESPONSE_UNVERIFIED';
   return 'DISPATCHED_EXISTING_WORLD_SYNC_ONCE_VIA_PAGES';
 }catch{
   // Partial delivery is possible. NEVER blindly retry within one cron tick.
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
