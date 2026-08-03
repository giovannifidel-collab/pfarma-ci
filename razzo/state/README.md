# RAZZO Factory Live Status

- **Factory:** `RUNNING`
- **Mode:** `PILOT`
- **Updated:** `2026-08-03T21:13:00Z`
- **Observed control-plane SHA:** `09f34616be712c7987976685faec5df137f2d770`
- **Enabled cells:** `RAZZO-Cell-00`
- **Active capability:** `none`
- **Global lease:** `FREE`
- **Pilot limits:** `1` capability / `2` shreds
- **Live operations issue:** `#753`

## Active boundary

Only `RAZZO-Cell-00` is authorized. It may handle one capability at a time with at most two independent shreds. Integration requires exact-head Product CI and independent Robot QA on the same candidate SHA. All higher-risk surfaces remain gated.

## Coordination contract

`razzo/state/global-lease.json` is the canonical global lease record. A trigger must acquire it with compare-and-swap semantics before creating product work. Exactly one contender may win; stale writers must fail closed. Expired leases are recoverable and capability binding is idempotent for the owning run.

## Total system simulation

```bash
python -m razzo.kernel.system_test --runs 1000 --contenders 5 --report /tmp/razzo-system-test-report.json
```

The test validates portfolio discovery, lease race handling, stale exact-SHA rejection, project coverage and authorization boundaries.

## Last heartbeat

- **Cell:** `RAZZO-Cell-00`
- **State:** `START_AUTHORIZED`
- **Observed:** `2026-08-03T21:13:00Z`
- **Message:** Owner restart authorized after the repaired total-system test; protected pilot start enabled.

> Machine-readable status: `razzo/state/factory-status.json`.
> Machine-readable lease: `razzo/state/global-lease.json`.
