# RAZZO Universal Operator Command

## Canonical command

`CHIUDI MACROCICLO`

Backward-compatible alias: `AVANZA TUTTO`.

Both commands resolve to the same closure-first execution contract. `AVANZA TUTTO` MUST NOT restore the old generic-progress semantics.

## Primary invariant

For every enabled project, the purpose of each invocation is to convert the current active macrocycle into a certified `COMPLETED` macrocycle in the same invocation whenever safely possible.

The execution target is not "make progress". The execution target is:

`ACTIVE MACROCYCLE -> SATISFY EXIT CRITERIA -> EXACT-SHA CI -> INDEPENDENT REVIEW -> ROBOT VERIFY -> INTEGRATE -> POST-MERGE REPLAY -> COMPLETION RECEIPT -> COMPLETED -> ACTIVATE NEXT`

If closure is not yet possible, execute only work that directly satisfies a missing exit criterion or removes a named completion blocker. Do not spend execution budget on unrelated discovery, polish, generic hardening, speculative future work, duplicate checks or administrative churn.

## Resolution rule

On every execution:

1. read `razzo/protocol.json`;
2. read the registry named by `portfolioRegistry`;
3. select every project with `enabled: true`;
4. read `razzo/macrocycle-state.json` and identify the active macrocycle for every enabled project;
5. reconcile live GitHub state before trusting persisted PR/SHA/gate fields;
6. evaluate every active macrocycle exit criterion;
7. fan out safe closure work independently across all enabled projects;
8. continue through certification and receipt whenever closure becomes reachable;
9. activate the next declared macrocycle immediately after certified closure.

Never require the operator prompt to be edited when projects are added, removed, renamed or reprioritized.

## Product-programmer invariant

Planning is not product progress. A planner artifact, queue entry, discovery candidate or generated work contract is only an intermediate object.

When an active macrocycle contains a safely implementable missing criterion, RAZZO MUST dispatch a product-writing executor capable of changing the authoritative product repository, testing the change, publishing an exact candidate SHA and opening or updating the integration PR. A `plan-only` execution MUST NOT satisfy a productive trigger when safely executable closure work exists.

A productive trigger may end without product code only when all currently missing criteria are either already awaiting external CI/review/replay evidence, blocked by a true scoped human gate, or genuinely require an unavailable infrastructure capability. Persist the exact reason.

## Closure-first cycle

For every enabled project, independently and in parallel:

### 1. RECONCILE

Read the live integration-lane head, open PRs, exact-SHA checks, receipts, pending human gates and active macrocycle state. Reuse valid evidence. Do not repeat already-green checks without an evidence reason.

### 2. FIND THE EARLIEST MISSING CLOSURE GATE

Inspect the active macrocycle exit criteria in order. Select work only if it:

- directly satisfies a `MISSING` exit criterion;
- removes a named blocker preventing that criterion;
- produces required exact-SHA CI/review/Robot evidence;
- integrates a verified candidate;
- performs required post-merge replay;
- emits the completion receipt.

### 3. BUILD REAL PRODUCT WORK

If code is missing, inspect the authoritative product repository and implement the smallest coherent vertical slice that satisfies the criterion. Use safe parallel workstreams only when the dependency graph justifies them.

Do not substitute previews, dashboards, canaries, docs, refactors or control-plane edits for the actual capability named by the criterion.

### 4. VERIFY AND INTEGRATE

Run relevant product tests, exact-SHA CI, independent review and Robot verification. Integrate only into the authorized integration lane and only from verified exact SHA.

### 5. CLOSE

When all criteria and gates are verified:

- perform required post-merge replay;
- persist completion receipt;
- mark macrocycle `COMPLETED`;
- activate the next declared macrocycle immediately.

Do not stop at PR open, PR merged, partial green CI, candidate receipt or queued replay.

## Human gates are non-blocking to autonomous work

A true human gate blocks only the exact sensitive action and strictly dependent work.

When one appears:

1. persist it to `pendingHumanGates` with project, macrocycle, criterion, exact required human action and evidence needed after resolution;
2. notify the operator;
3. leave the gated macrocycle open/deferred rather than falsely certifying it;
4. advance the autonomous execution cursor to safe independent work, including later macrocycles when dependencies permit;
5. continue all other enabled projects;
6. revisit pending gates on every trigger.

Human gates may accumulate. They are a backlog of small operator actions, not a global stop condition.

## Scheduler semantics

Every scheduled or manual trigger is a `CHIUDI MACROCICLO` invocation. The scheduler is a watchdog and re-entry mechanism; it must dispatch real product execution when safely executable closure work exists.

The success metric is **certified macrocycles closed per trigger**, secondarily named exit criteria/gates eliminated. Commits, PR count, tests, artifacts, plans and waves are not success metrics by themselves.

## Dynamic portfolio rule

Project-specific instructions remain in `razzo/projects.json`, `razzo/macrocycle-state.json` and repository-local RAZZO manifests/policies.

The canonical operator command remains `CHIUDI MACROCICLO` regardless of project count. `AVANZA TUTTO` remains only a compatibility alias.

## End-of-invocation invariant

For every enabled project, an invocation must end in one of these truthful states:

- the active macrocycle was certified `COMPLETED` and the next was activated;
- one or more named exit criteria were materially satisfied and the remaining earliest missing gate is persisted;
- a true scoped human/infrastructure gate was persisted and safe independent execution continued elsewhere.

It must never end merely because a plan was generated, a PR was opened, a test was queued, or a generic wave completed.
