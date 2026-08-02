# RAZZO Organism 2-2-1

## Purpose

Organism 2-2-1 is a programming method for a free, fast, parallel and fictional multi-agent factory without Codex, OpenAI API, GitHub Models, Copilot or another paid coding provider.

It does not pretend that GitHub Actions can reason. One ChatGPT execution supplies the intelligence; GitHub is the persistent blackboard and execution fabric; GitHub Actions supplies deterministic parallel build, test and exact-head verification.

## Core idea

One Delivery Objective becomes one **programming cell**. The cell contains five fictional roles executed as isolated reasoning passes over the same exact repository state:

Phase 0, parallel:

1. `CARTOGRAPHER` maps only the required repository surfaces and forbidden areas.
2. `SPECIFIER` converts the user outcome into invariants, acceptance tests and failure oracles.

Phase 1, parallel and speculative:

3. `MAKER_MINIMAL` produces the smallest complete candidate.
4. `MAKER_ROBUST` independently produces a resilience-first candidate.

Phase 2:

5. `BREAKER` attacks both candidates and verifies their evidence.

A deterministic tournament selects one candidate. The assembler publishes only the winner on the canonical objective branch and opens or updates one canonical PR.

The method is therefore multi-agent in behaviour, but not in provider cost: the roles are fictional partitions of one intelligence, not five external AI services.

## Why 2-2-1

The role graph is:

```text
CARTOGRAPHER ─┐
              ├─> MAKER_MINIMAL ─┐
SPECIFIER ────┘                   ├─> BREAKER ─> one winner ─> one PR
              ┌─> MAKER_ROBUST ──┘
              └───────────────────
```

Two analysis passes run independently, then two implementation candidates are developed independently, then one adversarial pass chooses what survives.

This creates real useful parallelism while preventing the historic failure mode of one PR per worker.

## Non-negotiable invariants

- one Delivery Objective fingerprint;
- one exact base SHA;
- one canonical objective branch;
- one canonical PR marker and one product PR;
- no run ID in the canonical branch identity;
- no duplicate candidate role or candidate SHA;
- maximum five logical roles and maximum two concurrent reasoning lanes inside one cell;
- all candidates cover every acceptance criterion;
- all candidates have a real diff and focused test evidence;
- candidate selection is deterministic and evidence-based;
- Product CI and Robot Collaudatore verify the same final exact SHA;
- only the winning candidate is published;
- losing speculative refs are temporary and must be deleted after assembly;
- no private source, patch or secret is persisted in the public control plane.

## Free execution model

The model uses only capabilities already available:

- ChatGPT scheduled execution or direct connected-GitHub execution for the five role passes;
- GitHub repositories as persistent state and leases;
- GitHub Actions for build, test, matrix verification and receipts;
- repository-local deterministic tools for bounded edits and checks.

No separately billed model call is required.

## Speed model

A role does not rescan the complete repository. `CARTOGRAPHER` creates a narrow context map tied to the exact base SHA. Every later role consumes that map.

Both makers start from the same immutable base SHA and operate as alternatives. They do not wait for one another and they are never merged together mechanically. The tournament chooses the best complete candidate, avoiding conflict-heavy branch assembly.

GitHub Actions then fans out verification lanes on the selected exact candidate SHA:

- focused tests;
- product suite;
- boundary and forbidden-surface checks;
- static analysis/security checks;
- independent functional Robot QA.

## Multi-project model

Each enabled repository may own one active programming cell per non-colliding objective. Portfolio scheduling leases cells, not generic workers.

With five available execution opportunities, the governor prefers:

- two parallel cells on independent repositories or collision domains;
- two maker candidates inside each eligible cell when capacity permits;
- one verification/recovery slot;
- immediate refill when a cell enters CI wait or a local human gate.

Backpressure applies only to the affected objective, collision domain or repository.

## Candidate tournament

A candidate is eligible only when it:

- starts from the cell exact base SHA;
- has a unique candidate SHA;
- changes at least one allowed file;
- covers every objective acceptance criterion;
- passes focused tests and Product CI.

Among eligible candidates, selection is deterministic:

1. fewest unresolved risk flags;
2. smallest complete diff;
3. stable role preference;
4. candidate SHA tie-break.

This prevents subjective self-certification and ensures reruns select the same winner from the same evidence.

## Final delivery gate

The final receipt is valid only when all of these point to the same exact SHA:

- selected candidate;
- expected canonical branch head;
- Product CI;
- Robot Collaudatore.

A real diff and functional assertions are mandatory. Control-plane tests alone never count as product progress.

## Migration rule

Organism 2-2-1 does not reactivate the legacy V7 one-PR-per-worker workflow. Reusable exact-SHA, lease, collision, receipt and test components may be called by the new cell runtime, but branch identity, candidate publication and PR ownership follow the invariants above.

The first operational proof must be one non-hardcoded product objective completed end to end with:

- two fictional maker candidates or one documented safe fallback;
- one selected candidate;
- one canonical product PR;
- Product CI exact-head green;
- separate Robot QA exact-head green;
- zero duplicate PRs;
- a self-replan decision for the next objective.
