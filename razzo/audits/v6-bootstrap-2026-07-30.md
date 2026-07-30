# RAZZO V6 bootstrap audit — 2026-07-30

Canonical source loaded from GitHub:
- `razzo/protocol.json`
- `razzo/UNIVERSAL_COMMAND.md`
- `razzo/projects.json`
- `razzo/project-state.json`

## Verified facts

- Protocol version: 5, execution engine compatibility: `RAZZO_V6_V7`.
- Dynamic registry is enabled.
- Enabled projects: `project-giovanni`, `pfarma-cloud`, `family-cloud`.
- Five universal `RAZZO AVANZA TUTTO` automations exist at minutes 00/12/24/36/48 and use the same complete-cycle role.
- Legacy phase-specialized automations are disabled.
- `razzo/project-state.json` is stale: all three queue hints currently point to issues already closed as completed.
- PFarma GEN-0002 remains the current safe product workstream through `pfarma-cloud#2028`, `pfarma-cloud#2029`, and `pfarma-ci#716`.

## Operational classification

| Capability | State | Evidence / deficit |
|---|---|---|
| Portfolio discovery | REAL | Dynamic enabled registry in `razzo/projects.json`. |
| Product discovery | REAL | Canonical command requires discovery when ready=0; GEN-0002 was discovered from runtime code. |
| Work queue | PARTIAL | Issue-backed work exists, but canonical project-state queue hints are stale and no verified resumable queue contract was established in this audit. |
| Dispatcher | PARTIAL | Shard execution and exact-SHA workflows have run, but a general registry-driven dispatcher was not verified in this audit. |
| Workers / shards | REAL | Prior independent shard executions and receipts exist. |
| Execution receipts | REAL/PARTIAL | Product GEN-0001 and Phase 4 receipts exist; universal per-cycle receipt coverage remains unverified. |
| Aggregator / verifier | REAL/PARTIAL | Exact-SHA product gates and Phase 4 certifier exist; universal queue-wide aggregation remains unverified. |
| Telemetry | PARTIAL | Protocol defines metrics, but current canonical measured cycle telemetry was not found during this bootstrap. |
| Generation promotion | REAL | GEN-0001 was promoted only after product code, tests, exact-SHA gates, merge, and receipt. |

## Fail-closed status

`RAZZO V6 NON ANCORA OPERATIVA`

Missing acceptance evidence:
- current non-stale canonical queue;
- verified general dispatcher lifecycle/lease/idempotency across the dynamic portfolio;
- current aggregate cycle receipt with measured concurrency telemetry;
- a fresh multi-workstream V6 wave through queue -> dispatch -> workers -> receipts -> verifier.

## Immediate next execution

1. Complete PFarma GEN-0002 runtime change on draft PR `pfarma-cloud#2029`.
2. Freeze its exact head.
3. Run PFarma Executor and Hosted Product Gate on the same SHA.
4. Merge with expected-head protection and emit GEN-0002 receipt.
5. Refresh canonical project state from live GitHub evidence.
6. Execute a fresh multi-workstream operational wave and record aggregate telemetry.
