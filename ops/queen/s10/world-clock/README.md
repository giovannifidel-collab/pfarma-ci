# S10 — single World observation clock using EXISTING Cloudflare Access + Pages credentials

This remains exactly the existing one S1 event loop, one School S2, and original GitHub World observer/writer. There is no new Queen, paid provider, Neon write or second World source.

## Credential reuse: NO new GitHub PAT

- Existing Cloudflare Pages production `hive-alveare` has encrypted `HIVE_GITHUB_DISPATCH_TOKEN`, already used for repository_dispatch. It NEVER leaves Pages.
- Existing `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` are available in the relay's trusted GitHub Actions environment. On an **exact Owner-signed release only**, upload these two existing values as encrypted Worker secrets, NEVER log them or commit values.
- One minute Worker `hive-queen-world-clock` reads public relay World source (raw GitHub, authoritative `generated_at`) and the existing World workflow queue. It calls the fixed HTTPS Pages `/api/s10-world-clock-dispatch` endpoint **only** if the genuine source is >=10 minutes old and no active/recent World job.
- The Pages endpoint is protected by existing Cloudflare Access service credentials. It independently verifies the signed JWT (RS256, Cloudflare signing key, exp, audience format, and pinned SHA256 of existing Access service client ID); validates the minute tick and original World freshness/queue again, then dispatches only `hive_world_clock_tick` to the original `pfarma-ci` repository. No open general-purpose dispatch API.
- Original `hive-world-sync.yml` listens only to this exact repository_dispatch type, manual workflow_dispatch and the existing config push. Its old GitHub cron is removed **only when the new Worker is activated during an Owner-approved atomic cutover**. Original fingerprint-only S1 wake and World timestamp source checks stay unchanged.
- Worker `fetch()` responds 404 to all HTTP requests. Its cron alone is `* * * * *`. Two independent read-only fresh World postflight observations and watchdog recovery are mandatory for terminal S10.

## Exact release order; no duplicate clocks

1. Source-only CI PASS on the HIVE Pages broker PR and this relay PR; exact two PR SHA and audit HIVE/relay main.
2. Fresh exact-scope Owner OIDC signature ratifying the existing service-token transfer and two precise source PRs; no old OIDC lease reused.
3. Stage Worker with `wrangler.disabled.jsonc` (no cron, `CLOCK_ENABLED=false`). Upload **only the two existing Access values**, verify Pages endpoint Access live with authenticated header and JSON; confirm existing Pages token scope for repository_dispatch.
4. Merge both exact Owner-approved source PRs in strict order, update HIVE relay pointer if required, verify Pages deployment live without broadening other projects. Do not activate cron until both Pages broker and original World workflow are available.
5. Deploy same Worker with `wrangler.jsonc`; original GitHub World cron must be absent. Confirm single Cloudflare schedule, two authentic triggered World observations separated >=480 s, World true source freshness <=1800s and original S1 semantics.
6. Check S1, Cognitive, School, Neon, watchdog, no unverified training, anti-replay, free-plan consumption, zero paid fallback and verified rollback. Update HIVE issues #102/#103 only with truthful evidence.

## Rollback

Deploy **the same** Worker with `wrangler.disabled.jsonc`, removing its cron and disabling egress. The Pages broker is access-gated but never scheduled itself. Restore old GitHub cron **only through a separate fresh exact Owner signed rollback step** (or pre-authorized bounded rollback in the same exact-scope OIDC lease); never run overlapping clocks.

## CI is not deployment

The source-only tests reject wrong JWT, wrong actor/service, bad issuer, stale/future clock, invalid World source, active/recent World job, unknown dispatch response and any public trigger path. HIVE PR #105 source CI #44630161220 PASS. Relay live readiness preflight #44629277082 showed an existing authenticated Cloudflare Pages GET succeeds with HTTP 200 JSON using descriptive User-Agent; default Python urllib 403 was Pages Browser Integrity Check.

Cost: one Cron tick/min ~1440 daily; the Cloudflare Workers Free plan limit is 100000 requests/day, subject to real account plan and existing usage. Never enable provider charges without explicit approval.

NO PRODUCTION CUTOVER UNTIL OWNER OIDC AND LIVE POSTFLIGHT PASS.
