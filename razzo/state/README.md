# RAZZO Factory Live Status

- **Factory:** `PAUSED`
- **Mode:** `PILOT`
- **Updated:** `2026-08-03T20:20:19Z`
- **Observed control-plane SHA:** `f92de10a0bee1f21dcc0bc2ed3be36dd02352671`
- **Enabled cells:** `none`
- **Active capability:** `none`
- **Global lease:** `FREE`
- **Pilot limits:** `1` capability / `2` shreds
- **Live operations issue:** `#753`

## Stop boundary

The owner stop is authoritative. All ChatGPT RAZZO automations are disabled. No product dispatch, branch creation, pull request creation, integration merge or production action is authorized while this state remains `PAUSED`.

## Coordination contract

`razzo/state/global-lease.json` is the canonical global lease record. A trigger must acquire it with compare-and-swap semantics before creating product work. Exactly one contender may win; stale writers must fail closed. Expired leases are recoverable and capability binding is idempotent for the owning run.

## Total system simulation

The non-mutating test entry point is:

```bash
python -m razzo.kernel.system_test --runs 1000 --contenders 5 --report /tmp/razzo-system-test-report.json
```

It validates the dynamic portfolio, paused boundary, global lease race handling, stale exact-SHA rejection, enabled-project coverage and zero product writes/merges. GitHub Actions publishes the JSON report as an artifact.

## Last heartbeat

- **Cell:** `RAZZO-Cell-00`
- **State:** `DISABLED`
- **Observed:** `2026-08-03T20:20:19Z`
- **Message:** Owner stop confirmed. All RAZZO automations are disabled; no product dispatch or merge is authorized.

> Machine-readable status: `razzo/state/factory-status.json`.
> Machine-readable lease: `razzo/state/global-lease.json`.
