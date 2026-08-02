# RAZZO Capability Factory — pre-launch gate

This branch contains only pre-launch engineering and a fixture-only protected pilot.

Completed stages:

1. Capability identity and revision separation.
2. Fail-closed DAG and wave validation.
3. Canonical bridge across the controller and execution objective models.
4. Idempotent runtime journal, collision leases and exact-head gates.
5. Fault simulation, shadow mode and a non-mutating protected pilot.

Progressive product activation is deliberately excluded. Production remains blocked until an eligible autonomous provider is verified, a human approves activation, product writes are explicitly enabled, repository-local execution contracts exist, and exact-head Product CI plus independent Robot QA are available.

No code in this branch authorizes automatic production merges.