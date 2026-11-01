// Conservative public-only rescue for orphaned queued PLUS jobs. The public
// workflow triggers the ONLY executor. Existing DB claim is atomic.
const base = (process.env.SUPABASE_URL || "").replace(/\/$/, "");
const token = process.env.SUPABASE_SERVICE_ROLE_KEY;
const github = process.env.GITHUB_TOKEN;
const repo = "giovannifidel-collab/pfarma-ci";
if (!base || !token || !github) throw new Error("Missing trusted bridge credentials");
const headers = {Authorization:`Bearer ${token}`,apikey:token};
const response = await fetch(`${base}/rest/v1/preparatore_v2_jobs?status=eq.queued&select=id,created_at,expires_at&order=created_at.asc&limit=15`,{headers,signal:AbortSignal.timeout(12000)});
if (!response.ok) throw new Error(`Queue verification failed (${response.status})`);
const now=Date.now();
const rows=await response.json();
let count=0;
for(const item of rows){
  if (!/^[a-f0-9]{8}-[a-f0-9-]{27,36}$/i.test(item.id || "")) continue;
  const created=Date.parse(item.created_at),expires=Date.parse(item.expires_at);
  if (!Number.isFinite(created)||!Number.isFinite(expires)) continue;
  if (now-created<120000||expires<=now+180000) continue;
  if (count>=4) break;
  const res=await fetch(`https://api.github.com/repos/${repo}/dispatches`,{
    method:"POST",
    headers:{Authorization:`Bearer ${github}`,Accept:"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","Content-Type":"application/json"},
    body:JSON.stringify({event_type:"preparatore-v2-request",client_payload:{job_id:item.id}}),
    signal:AbortSignal.timeout(12000)
  });
  if(res.status!==204)throw new Error(`Public queued-job recovery failed (${res.status})`);
  count++;
}
console.log(`Public bridge queued-job rescue dispatched ${count} candidate jobs; atomic claim prevents duplicate execution.`);
