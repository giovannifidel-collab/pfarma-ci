const jobId = process.argv[2] || process.env.PREPARATORE_JOB_ID;
const supabaseUrl = required("SUPABASE_URL").replace(/\/$/, "");
const serviceKey = required("SUPABASE_SERVICE_ROLE_KEY");

if (!jobId || !/^[0-9a-f-]{36}$/i.test(jobId)) throw new Error("Invalid job id");

function required(name) {
  const value = process.env[name];
  if (!value) throw new Error(`Missing ${name}`);
  return value;
}

function headers() {
  return { Authorization: `Bearer ${serviceKey}`, apikey: serviceKey };
}

async function getJson(path) {
  const response = await fetch(`${supabaseUrl}/rest/v1/${path}`, {
    headers: headers(),
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Supabase lookup failed (${response.status})`);
  return response.json();
}

const jobs = await getJson(`preparatore_v2_jobs?id=eq.${jobId}&select=user_id,status&limit=1`);
const job = jobs[0];
if (!job || typeof job.user_id !== "string") throw new Error("Job not found");
if (!["queued", "running"].includes(job.status)) throw new Error("Job is not actionable");

const accessRows = await getJson(`preparatore_v2_access?user_id=eq.${encodeURIComponent(job.user_id)}&enabled=eq.true&select=user_id&limit=1`);
if (!accessRows[0]) throw new Error("Photo AI access is disabled for this user");

const output = process.env.GITHUB_OUTPUT;
if (!output) throw new Error("Missing GITHUB_OUTPUT");
const { appendFile } = await import("node:fs/promises");
await appendFile(output, `user_id=${job.user_id}\n`, { encoding: "utf8" });
process.stdout.write("Photo AI user access verified.\n");
