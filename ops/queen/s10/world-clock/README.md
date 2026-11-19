# S10 — replacement World observation time authority (Owner-gated)

## What this is — and is not

This is a **single replacement clock**, not a new Queen, S1, School, autonomous dispatcher or scheduler for arbitrary projects. It runs an extremely small Cloudflare `scheduled()` tick each minute. Only after inspecting the **real** authoritative, sanitized World source and the existing GitHub World Sync run queue does it send **one** `workflow_dispatch` to `hive-world-sync.yml` on `pfarma-ci/main`, when the previous genuine observation is at least 10 minutes old. The original World Sync rebuilds all upstream sources, records an authenticated timestamp, and notifies the **existing single S1** only when the semantic fingerprint changes.

The existing GitHub Actions `on.schedule` is REMOVED in the candidate source release. GitHub's best-effort five-minute `schedule` is *not* a live heartbeat SLA. No timestamp is synthesized by the Worker, no World data is written by the Worker, and a one-minute Cloudflare tick does **not** imply a one-minute full GitHub job.

## Security and credentials (never commit secret values)

- Configure **one dedicated GitHub fine-grained PAT**, owned by the GitHub repository Owner, restricted exclusively to `giovannifidel-collab/pfarma-ci`, with **Actions: Read/Write** and **Contents: Read** (and required Metadata: Read), a short expiry, and no access to HIVE private sources, other repositories, settings, admin, secrets, project writes, packages or workflows. The Worker needs to read the public World snapshot and World workflow runs, then invoke this one existing World workflow.
- Store the PAT as an encrypted GitHub Actions secret named `S10_WORLD_CLOCK_GH_TOKEN` **only for the Owner-approved Cloudflare deployment**. The release job must upload it as the encrypted Worker secret `GH_WORLD_DISPATCH_TOKEN`. No PAT in repo files, command output, logs, event payload, or Worker plaintext vars. Do not reuse the broad `PFARMA_SOURCE_TOKEN`.
- Cloudflare deployment needs the existing Cloudflare API token with Worker Scripts and Cron Trigger write capability and the verified target account. Staging/rollback config has **no Cron Trigger** and `CLOCK_ENABLED=false`.
- No authenticated HTTP endpoint exists on this Worker; all HTTP requests return 404.
- Missing secret, stale/delayed tick, invalid World JSON, future source time, GitHub source/read errors, active/recent World job, and uncertain dispatch outcomes fail closed. The Worker never retries a dispatch in the same tick.
- Existing GitHub World Sync concurrency, bounded optimistic retries and semantic-only S1 wake remain unchanged. Clock tick metadata is validated but is not source freshness evidence.
- Owner OIDC and project source SHA checks are required to merge, configure, activate and/or roll back. The standing L0–L2 HIVE grant alone does not authorize any of these production changes.

## Source and rollback

- Candidate main: `wrangler.jsonc` -> `hive-queen-world-clock` with `* * * * *` and `CLOCK_ENABLED=true`.
- Safe stage/disable: `wrangler.disabled.jsonc` -> **same Worker**, `crons=[]` and `CLOCK_ENABLED=false`.
- Minimum safe release sequence: strict exact-SHA owner OIDC; run isolated negative tests; verify dedicated PAT scopes; deploy Worker **disabled**; add its GitHub secret; merge exactly the approved source PR that removes the old GitHub cron; activate **only this Worker** using active config; verify Cloudflare Cron schedule and real World Sync dispatch; verify 2+ separate genuine Worker ticks and fresh authenticated snapshots.
- If activation or GitHub dispatch fails, use the authorized disabled config; re-enable the original GitHub schedule **only** through a separate exact Owner-approved rollback or an explicitly signed rollback step. Do not silently run two time authorities indefinitely.
- Cloudflare Cron Trigger propagation can require several minutes. Source freshness goal remains `world.max_age_seconds=1800`, irrespective of whether Worker scheduling or external APIs are healthy.
- A green CI on this proposal certifies only *source correctness*, not that a Cloudflare Cron fired or that S10 reached terminal PASS. Signed live receipt requires actual scheduled ticks, successful World jobs, canonical S1 behavior, School zero unverified training, rollback and watchdog health.

## Cost and usage

At 1 tick/minute, ~1,440 short cron invocations/day; full GitHub World jobs are due approximately every 10+ minutes, **not** every minute. Keep within the account's **existing Free tier**, with no paid fallback. Check actual usage and account plan before enabling; fail closed if the plan or API entitlements are unknown.

This source proposal is designed for HIVE S10 gates G3/G4/G7/G8 and preserves S7 scoped compute routing DENY and S8 cross-project write DENY.
