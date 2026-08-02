# RAZZO Objective Kernel

This directory starts the replacement model for the legacy worker-oriented V7 runtime.

## Delivery invariant

One product objective owns one deterministic fingerprint, one canonical branch, zero or more subordinate shred branches, one candidate SHA, one product pull request, one exact-head product CI verdict, one exact-head independent QA verdict, and at most one merge.

A green control-plane workflow is not product progress. Product progress exists only after a candidate SHA is verified by the product repository and the independent Collaudatore against the same exact SHA.

## Canonical hierarchy

- `DeliveryObjective`: the user-visible outcome and acceptance boundary.
- `ShredContract`: one bounded implementation responsibility derived from the objective.
- `Candidate`: the assembled exact commit proposed by the objective branch.
- `Product CI`: repository-authoritative checks on the candidate SHA.
- `Collaudatore`: independent behavioral verdict on the candidate SHA.
- `Merge Gate`: permits integration only when both exact-head verdicts match the candidate.

## Branches

- Objective: `razzo/o/<objective-fingerprint-prefix>`
- Shred: `razzo/o/<objective-fingerprint-prefix>/s/<shred-id>`

Run IDs are deliberately excluded. Retrying an objective must recover or update the same canonical workspace instead of opening a duplicate branch or pull request.

## Current scope

The first kernel increment implements:

- deterministic objective identity;
- objective and shred branch identity;
- bounded objective state transitions;
- shred DAG validation;
- exact candidate/CI/QA SHA equality gate;
- fail-closed tests for invalid transitions and mismatched SHA evidence.

It does not yet enable automatic production, dispatch builders, open pull requests, or merge product code.

## Migration rule

Legacy V7 remains frozen. New behavior must be developed on the `razzo/objective-kernel-v1` branch until the kernel, repository-local execution contracts, single-PR assembler, product CI gate, and Collaudatore are proven together on one real pilot objective.
