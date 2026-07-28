# RAZZO Universal Operator Command

## Canonical command

`AVANZA TUTTO`

## Resolution rule

The command has no static project list. On every execution:

1. read `razzo/protocol.json` from the canonical control plane;
2. read the registry named by `portfolioRegistry`;
3. select every project with `enabled: true`;
4. read each project's current canonical ref, integration lane, task graph, policy/executor hints and repository-local constraints;
5. treat GitHub as the source of truth and reconcile only what is necessary to execute product work safely.

Never require the operator prompt to be edited when projects are added, removed, renamed, reprioritized or moved to a different integration lane. Those changes belong in the registry or repository-local manifest.

## Product-first invariant

RAZZO exists to advance products, not to manufacture control-plane activity.

Control-plane work — refs, snapshots, checkpoints, CI routing, task-graph edits and orchestration — is subordinate to real product progress and should remain a minority of useful cycle work unless infrastructure repair is actually blocking product execution.

Do not use noop commits, nominal generation increments, synthetic benchmark churn or administrative PRs as a substitute for progress.

## Cycle

For every enabled project:

### 1. FAST RECONCILE

Reconcile the minimum required state: current exact ref, integration lane HEAD, open PRs, exact CI, task graph, collision domains, backpressure and human gates.

Do not spend the cycle repeatedly reconciling already-coherent state.

### 2. PRODUCT DISCOVERY

Inspect the real repository and identify useful, safe work beyond the declared ready queue, including:

- missing or incomplete capabilities;
- broken user journeys and regressions;
- TODO/FIXME/placeholder/mock paths that can safely become real;
- disconnected components;
- UX and accessibility gaps;
- missing validation or error handling;
- security and privacy hardening;
- resilience, offline, recovery and failure handling;
- performance and observability;
- useful tests and realistic robot/browser journeys;
- integration work that becomes possible after previous waves.

Repository-local vision, architecture, policies and task graphs override generic assumptions.

### 3. READY ZERO IS NOT STOP

`ready == 0` MUST trigger product discovery and self-replan before saturation can be declared.

A human gate freezes only the gated action. Continue safe work around it.

A project may be considered genuinely saturated only when all are true:

- no runnable work exists;
- no safe PR is integrable;
- product discovery finds no further meaningful safe work;
- all remaining meaningful advancement truly requires a human gate.

### 4. PLAN REAL WORK

Turn discovered work into atomic, independently verifiable workstreams.

Prefer real parallel work over one giant PR. Generate as many workstreams as the actual dependency graph justifies; never inflate task counts for appearance.

Each workstream needs a concrete expected result, collision domain, target lane and verification method.

### 5. FAN-OUT

Use the portfolio controller and repository-local concurrency policy to maximize safe parallelism.

Prioritize:

1. regressions, security and broken flows;
2. user-facing vertical slices and incomplete capabilities;
3. integration between existing capabilities;
4. UX, quality, resilience and performance;
5. infrastructure changes that directly increase future verified product throughput.

Do not allow administrative work to consume most execution slots.

### 6. VERIFY

A result is complete only after real evidence exists on GitHub:

- inspect the diff;
- run relevant tests and exact-SHA CI;
- use functional robots/browser journeys/fault tests where available;
- fail closed on ambiguity;
- never invent a successful outcome.

### 7. INTEGRATE

Integrate only into the project's registry/repository-authorized integration lane.

Never assume `main` is writable. Respect repository-local promotion policy and human gates.

Use collision checks and integration backpressure.

### 8. RECURSE

After meaningful integration, rerun product discovery and ask:

> What useful safe work became possible because of this wave?

Continue:

`DISCOVER -> PLAN -> FAN-OUT -> BUILD -> VERIFY -> INTEGRATE -> DISCOVER`

for the available execution budget.

## Human gates

Use the protocol and repository-local policy. At minimum, require a real human decision for:

- real secrets or credentials;
- paid activation;
- destructive production operations;
- irreversible migrations;
- sensitive cryptographic release;
- mutation/deletion of irreplaceable real data.

Do not broaden a gate to unrelated safe work.

## Dynamic portfolio rule

Project-specific instructions must live in `razzo/projects.json` and/or repository-local RAZZO manifests/policies.

The operator command remains exactly `AVANZA TUTTO` regardless of the number of projects.

When a new enabled registry entry appears, begin managing it automatically on the next cycle. When disabled, stop allocating new work to it while preserving existing evidence/history.

## End-of-cycle invariant

Leave GitHub coherent, exact-ref verifiable and immediately resumable by the next scheduled or interactive `AVANZA TUTTO` execution.
