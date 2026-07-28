# HOMO NOVUS

HOMO NOVUS is the bio-inspired recursive development architecture that governs the existing RAZZO operational engine.

`AVANZA TUTTO` remains the canonical operator command.

RAZZO V6/V7 remains the execution metabolism: discovery, queueing, dispatch, workers, leases, receipts, exact-SHA verification, integration, backpressure and human gates.

HOMO NOVUS determines **what level of the product must evolve next, how deeply to decompose it, how to allocate parallel work, and how to prove that lower-level work has produced higher-level usable behavior**.

## Core model

The development hierarchy is recursive:

`ENERGY -> PRIMITIVE -> ATOM -> MOLECULE -> MACROMOLECULE -> CELL -> TISSUE -> ORGAN -> SYSTEM -> ORGANISM -> ECOSYSTEM`

Software mapping:

- **Energy** — compute, tokens, CI capacity, concurrency and wall-clock budget.
- **Primitive** — language/runtime/tool primitive.
- **Atom** — predicate, type, constant, schema field or indivisible operation.
- **Molecule** — small pure rule or composable logic unit.
- **Macromolecule** — function, handler, adapter or bounded implementation unit.
- **Cell** — independently testable component.
- **Tissue** — coherent capability.
- **Organ** — user-visible vertical slice.
- **System** — complete user journey or subsystem.
- **Organism** — human-usable product.
- **Ecosystem** — interoperating portfolio/product environment.

The hierarchy is semantic, not a forced naming convention. Repository-local architecture may use different names, but the same recursive logic applies.

## Phenotype-first rule

The operator defines the desired phenotype: product goal, priorities, acceptance boundaries and true human-gate decisions.

The operator must not be required to enumerate routine implementation steps.

For every enabled project HOMO NOVUS asks:

1. What would make this product meaningfully more useful to a human now?
2. What is the highest-level non-gated deficit preventing that state?
3. At what level does that deficit live: organism, system, organ, tissue, cell or lower?
4. How far must it be decomposed before safe independent work becomes executable and verifiable?
5. Which resulting workstreams can run in parallel without collision?
6. After lower-level verification, did the expected higher-level behavior actually emerge?

## Recursive decomposition

Start at the highest-level functional deficit, not at an arbitrary backlog item.

Descend only while decomposition creates one or more of:

- independent execution;
- safe parallelism;
- clearer interfaces;
- deterministic ownership/collision domains;
- stronger verification;
- smaller failure radius;
- easier integration.

Stop descending when further atomization increases coordination cost without increasing verified throughput.

This prevents both monolithic work and artificial micro-task inflation.

## Recursive composition

Verification is bottom-up **and** emergent.

A green lower-level unit is necessary but never sufficient evidence for a higher-level structure.

Typical evidence ladder:

`unit -> component -> capability -> vertical slice -> integration journey -> system -> human-testable organism`

After composing verified children into a parent, verify the parent's behavior explicitly.

Examples:

- unit tests do not prove an upload journey works;
- API tests do not prove a browser workflow is usable;
- multiple complete features do not prove the product is runnable;
- all repositories being green does not prove the ecosystem delivers its intended outcome.

## Homeostasis

Every development wave must preserve system viability.

Homeostatic invariants include:

- exact-SHA evidence;
- repository integrity;
- regression resistance;
- security and privacy boundaries;
- compatibility;
- recoverability;
- idempotency;
- collision safety;
- resumability;
- human-gate isolation.

A wave that creates apparent feature progress while destabilizing the organism is not successful development.

## Differentiation

Workers should specialize rather than all behave identically.

Specialization can include UI, API, data model, storage, integration, resilience, security, tests, browser robotics, performance or review.

Differentiated workers share:

- the same desired phenotype;
- canonical repository state;
- bounded interfaces;
- collision domain;
- acceptance contract;
- verification requirements.

Differentiation exists to increase parallelism without losing organism-level coherence.

## Metabolism

Compute is finite metabolic energy.

HOMO NOVUS must allocate tokens, workers, CI slots and elapsed time toward the highest expected verified increase in product utility per unit of cost, time and risk.

Do not saturate workers merely because capacity exists.

Prefer widening the DAG by valid recursive decomposition over inventing synthetic work.

If 1,000 workers exist but only 12 safe independent workstreams are currently justified, use 12. If recursive decomposition exposes 300 genuinely independent units, use the larger fan-out subject to provider and integration backpressure.

## Bottleneck dominance

The highest-level non-gated bottleneck dominates lower-value isolated feature accumulation.

Examples:

- a feature-rich application with no runnable UI prioritizes testable runtime;
- a runnable application with a broken primary user journey prioritizes that journey;
- a complete user journey with unsafe persistence prioritizes data integrity;
- a useful product blocked only by a real credential/paid/destructive gate freezes only that gated action and continues independent safe development.

## Feedback and adaptation

After every verified integration:

`OBSERVE -> COMPARE WITH PHENOTYPE -> LOCATE DEFICIT -> DECOMPOSE -> DIFFERENTIATE -> EXECUTE -> VERIFY -> COMPOSE -> TEST EMERGENCE -> INTEGRATE -> OBSERVE`

Do not assume the previous plan remains optimal after the product changes.

New capability may remove an old bottleneck and expose a higher-level one. Replanning is therefore mandatory.

## Human-testability rule

When enough lower-level structures exist, HOMO NOVUS must actively seek organism-level evidence.

Prefer making a product runnable and observable by a human over continuing to accumulate disconnected features.

Human-testability may use disposable/demo data and safe environments. It must never bypass real credential, paid activation, destructive production, irreversible migration, crypto-release or irreplaceable-data gates.

## Saturation

A project is not saturated because one branch is human-gated or because `ready == 0`.

True saturation requires all of the following:

- no runnable safe work exists;
- no safe PR can integrate;
- recursive decomposition finds no meaningful independent work;
- no higher-level user journey can be improved safely;
- no useful testability/integration/resilience work remains;
- every remaining meaningful next state requires a true human gate.

## Relationship to RAZZO

HOMO NOVUS does not discard RAZZO.

It governs it.

- HOMO NOVUS selects the next organism-level objective and decomposition depth.
- RAZZO performs operational discovery, queueing, dispatch, execution, receipts, verification and integration.
- HOMO NOVUS evaluates emergence and selects the next state.

Canonical loop:

`PHENOTYPE -> ORGANISM DEFICIT -> RECURSIVE DECOMPOSITION -> RAZZO DISPATCH/BUILD -> EXACT-SHA VERIFY -> RECURSIVE COMPOSITION -> EMERGENCE TEST -> INTEGRATE -> PHENOTYPE REASSESSMENT`

The result should be measured primarily by **verified increase in functional organization and human utility**, not by PR count, commit count, agent count or synthetic activity.