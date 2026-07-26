const supabaseUrl = required("SUPABASE_URL").replace(/\/$/, "");
const serviceKey = required("SUPABASE_SERVICE_ROLE_KEY");
const cutoff = encodeURIComponent(new Date().toISOString());

function required(name) {
  const value = process.env[name];
  if (!value) throw new Error(`Missing ${name}`);
  return value;
}
function headers(extra = {}) { return { Authorization: `Bearer ${serviceKey}`, apikey: serviceKey, ...extra }; }
function storageUrl(path) { return `${supabaseUrl}/storage/v1/object/preparatore-v2-jobs/${path.split("/").map(encodeURIComponent).join("/")}`; }
async function deletePhotos(paths) {
  for (const path of Object.values(paths || {})) {
    if (typeof path !== "string") continue;
    await fetch(storageUrl(path), { method: "DELETE", headers: headers() }).catch(() => undefined);
  }
}
const response = await fetch(`${supabaseUrl}/rest/v1/preparatore_v2_jobs?status=in.(queued,running)&expires_at=lte.${cutoff}&select=id,user_id,storage_paths&limit=100`, { headers: headers(), cache: "no-store" });
if (!response.ok) throw new Error(`Expired job lookup failed (${response.status})`);
const jobs = await response.json();
for (const job of jobs) {
  await deletePhotos(job.storage_paths);
  const patch = await fetch(`${supabaseUrl}/rest/v1/preparatore_v2_jobs?id=eq.${job.id}&user_id=eq.${job.user_id}&status=in.(queued,running)`, {
    method: "PATCH",
    headers: headers({ "Content-Type": "application/json" }),
    body: JSON.stringify({ status: "expired", error_code: "expired", error_message: "Analisi scaduta in sicurezza. Nessuna scheda è stata modificata.", completed_at: new Date().toISOString(), updated_at: new Date().toISOString() }),
  });
  if (!patch.ok) throw new Error(`Expired job update failed (${patch.status})`);
}
process.stdout.write(`Expired Preparatore V2 jobs cleaned: ${jobs.length}.\n`);
