# RAZZO Factory Live Status

- **Factory:** `RUNNING`
- **Mode:** `PILOT`
- **Updated:** `2026-08-03T21:10:00Z`
- **Observed control-plane SHA:** `9a8d298523f68ff44da3a163831a127e649c83e6`
- **Enabled cells:** `RAZZO-Cell-00`
- **Active capability:** `none`
- **Global lease:** `FREE`
- **Pilot limits:** `1` capability / `2` shreds
- **Live operations issue:** `#753`

## Active boundary

The owner restart is authoritative. Only `RAZZO-Cell-00` is authorized. It may operate on one product capability at a time with at most two independent shreds. It may merge only into registered integration lanes after exact-head Product CI and independent Robot QA both succeed on the same candidate SHA. Product `main`, production deploys, credentials, irreversible migrations and sensitive writes remain prohibited.

## Coordination contract

`razzo/state/global-lease.json` is the canonical global lease record. A trigger must acquire it with compare-and-swap semantics before creating product work. Exactly one contender may win; stale writers must fail closed. Expired leases are recoverable and capability binding is idempotent for the owning run.

## Total system simulation

The non-mutating test entry point is:

```bash
python -m razzo.kernel.system_test --runs 1000 --contenders 5 --report /tmp/razzo-system-test-report.json
```

It validates the dynamic portfolio, global lease race handling, stale exact-SHA rejection, enabled-project coverage and zero unauthorized product writes/merges. GitHub Actions publishes the JSON report as an artifact.

## Last heartbeat

- **Cell:** `RAZZO-Cell-00`
- **State:** `START_AUTHORIZED`
- **Observed:** `2026-08-03T21:10:00Z`
- **Message:** Owner restart authorized after the repaired total-system test; protected pilot start enabled.

> Machine-readable status: `razzo/state/factory-status.json`.
> Machine-readable lease: `razzo/state/global-lease.json`.
