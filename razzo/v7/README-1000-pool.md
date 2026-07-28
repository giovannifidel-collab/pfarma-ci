# RAZZO V7 logical 1000-worker pool

RAZZO V7 exposes a logical elastic product-worker pool of up to 1000 safe work items. GitHub Actions limits one job matrix to 256 generated jobs, so the worker fabric executes at most 250 collision-safe workers in a single physical wave. Event-driven continuation immediately schedules the next wave while real safe work remains.

The 1000-worker value is a logical portfolio burst ceiling, not a promise that 1000 hosted runners execute simultaneously. Actual concurrency remains bounded by GitHub account/runner availability, issue discovery, collision domains, exact-SHA validation, and human/destructive gates.

Safety invariants remain unchanged: no production writes, real EasyFarm/user-data writes, fiscal actions, paid infrastructure activation, secrets/credentials changes, destructive repair, irreversible migrations, or direct main writes by product workers.
