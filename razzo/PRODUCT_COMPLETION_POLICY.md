# RAZZO Product Completion Policy

This policy is mandatory for portfolio discovery, planning, fan-out, execution and reporting.

The machine-readable source is `razzo/product-completion-policy.json`.

## Core rule

RAZZO must maximize verified reduction in distance from the current repository state to a human-usable, persistent, end-to-end product state.

It must not optimize for pull-request count, commit count, test count, screen count, issue count or nominal generations.

## Capacity budget

Over every rolling five-generation window:

- at least 70% of useful execution capacity must address structural product bottlenecks;
- at most 20% may address secondary UX and product refinements;
- at most 10% may address Factory governance, analysis or infrastructure.

When the structural minimum is missed, the next safe generation must restore compliance before further secondary work is admitted.

## Selection rule

Before planning work, determine:

1. the project's primary human journey;
2. whether the product can be started or reached;
3. whether the primary journey completes end-to-end;
4. whether results persist across restart or reopen;
5. whether required real integrations operate;
6. whether realistic failure and recovery paths work;
7. the highest-impact non-gated structural deficit.

The highest-impact deficit becomes the parent workstream. Decomposition may expose safe child tasks, but it must not replace the parent objective with an indefinite series of isolated micro-features.

## Anti-gaming rule

The following do not constitute progress unless they directly execute or verify the selected structural workstream in the same generation:

- status, manifest or receipt churn;
- analysis without implementation;
- roadmap or issue creation;
- isolated readiness, summary or dashboard screens;
- hard-coded or mock-only behavior;
- query-only state standing in for required persistence;
- read-only preview pages standing in for required real operations;
- test-only changes for already known behavior;
- nominal generation increments.

## Completion evidence

Every claimed product advancement must state:

- the structural blocker removed;
- what a human can now do that was previously impossible;
- the exact candidate SHA;
- end-to-end or functional evidence appropriate to the capability;
- the next structural bottleneck.

Counts of PRs, commits, tests, agents or screens must not be presented as the principal result.

## Project directives

### Project Giovanni

Primary journey: assessment → plan → workout → atomic result publication → history → progression.

Prioritize Preparatore correctness, persistence, complete end-to-end progression, production E2E verification and direct user testability. Deprioritize additional dashboards, summaries and parallel guidance pages until the primary journey is complete and reliable.

### PFarma Cloud

Primary journey: operator access → real operational data → action → persistence → audit → recovery.

Prioritize a startable product, real persistence, progressive EasyFarm or operational-source integration, real inventory/reservations/customers/orders/documents/lots/expiries, backup and traceability. Deprioritize further demo-only cockpits and preview pages until the real operational journey advances.

### Family Cloud

Primary journey: authenticate → upload → persist → browse timeline/albums → reopen → recover → synchronize.

Prioritize single-command runtime, reachable deployment, authentication, real upload, persistence, storage, synchronization, Family Node and recovery. Do not classify additional browser-local galleries or read-only insights as completion of a cloud capability.
