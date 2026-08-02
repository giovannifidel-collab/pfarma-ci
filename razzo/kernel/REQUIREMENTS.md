# RAZZO Canonical Development Contract

This document is the single active specification for the Objective Kernel. Older V5/V6/V7 operational instructions remain historical evidence but do not override this contract when they conflict with it.

## Mission

RAZZO transforms one product objective into one verified, integrable product pull request.

A delivery is successful only when all of the following are true:

- the objective was not hard-coded as solution code in the control plane;
- the exact product base SHA was recorded before planning;
- the Planner produced a dependency-aware DAG of independently executable shreds;
- builders produced real non-empty commits inside bounded surfaces;
- the objective was assembled into one canonical branch;
- at most one open PR exists for the objective fingerprint;
- Product CI passed on the exact candidate SHA;
- the independent Collaudatore passed the same candidate SHA;
- expected-head protection passed immediately before merge;
- the merge SHA is recorded;
- no duplicate objective, branch or PR was created;
- the system reassessed the product after merge.

## Permanent invariants

1. GitHub is the source of truth.
2. Product progress means a verified product change, not workflow activity, receipts or governance churn.
3. One objective fingerprint owns one canonical branch and at most one open PR.
4. Run IDs never participate in objective identity or canonical branch naming.
5. The control plane may define contracts and constraints, but must not contain the completed product solution.
6. Every action is bound to an immutable exact input SHA.
7. Every merge is bound to one candidate SHA verified by both Product CI and Collaudatore.
8. Any ambiguity, stale base, missing evidence or SHA mismatch fails closed.
9. Human gates block only the sensitive action that requires human authority.
10. Scheduled triggers are recovery watchdogs, not the primary progress engine.
11. Parallelism follows the real DAG and measured capacity. The initial global builder limit is five.
12. Private source, credentials and generated product code are never persisted in public control-plane artifacts.

## Canonical lifecycle

`DISCOVERED -> PLANNED -> BUILDING -> ASSEMBLING -> CANDIDATE -> VERIFYING -> VERIFIED -> MERGE_READY -> MERGED -> COMPLETED`

Failure or recovery states:

- `BLOCKED_HUMAN`
- `BLOCKED_ENVIRONMENT`
- `NEEDS_REPLAN`
- `FAILED`
- `SUPERSEDED`

No state may be inferred from a workflow conclusion alone. Each transition requires evidence defined in `requirements.json`.

## Roles

### Portfolio Reconciler

Loads enabled projects dynamically, reads current integration heads, open objective PRs, checks and human gates from GitHub.

### Planner

Inspects the exact product checkout and converts one objective into a bounded DAG. It defines responsibilities, interfaces, dependencies, allowed surfaces and acceptance subsets. It does not write the final implementation.

### Builders

Operate in isolated workspaces on one shred each. They may commit only bounded product changes and focused tests. They do not open product PRs.

### Objective Assembler

Composes verified shred commits into the one canonical objective branch. It owns conflict detection and candidate creation.

### Product CI

Runs repository-local setup, build and test commands on the exact PR candidate SHA.

### Collaudatore

Independently tests user-visible acceptance criteria on the same candidate SHA. It emits only `PASS`, `FAIL` or `INCONCLUSIVE` with evidence.

### Merge Gate

Confirms objective identity, single-PR invariant, candidate SHA equality, Product CI, QA, expected integration head and policy before merge.

### Continuation Engine

After merge, reconciles the new product state and selects or creates the next useful objective. It never treats an empty static queue as proof of saturation.

## Superseded patterns

The following patterns are explicitly non-canonical:

- one PR per worker;
- branch names containing workflow run IDs;
- static solution recipes in discovery, worker or assembler code;
- static project-state snapshots authorizing execution;
- nominal 64/300/1000 worker capacity without measured proof;
- control-plane CI substituting for product PR CI;
- receipts self-certifying delivery;
- a green aggregate verifier despite failed product work;
- five ChatGPT timers acting as the production engine.

## Traceability

`requirements.json` is the machine-readable requirement-to-component-to-acceptance matrix. Every implementation PR for the new kernel must identify the requirement IDs it advances and add or update executable tests.

The kernel is not operational until `RZ-020` passes on a real, non-hard-coded product objective.
