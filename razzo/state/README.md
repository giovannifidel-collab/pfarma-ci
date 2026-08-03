# RAZZO Factory Live Status

- **Factory:** `RUNNING`
- **Mode:** `PILOT`
- **Updated:** `2026-08-03T21:24:00Z`
- **Observed control-plane SHA:** `44e5812bbb284f02866ad6ff0d51876de4d8f5db`
- **Enabled cells:** `RAZZO-Cell-00`
- **Active capability:** `none`
- **Global lease:** `FREE`
- **Pilot limits:** `1` capability / `2` shreds
- **Live operations issue:** `#753`

## Active boundary

Only `RAZZO-Cell-00` is authorized. It may handle one capability at a time with at most two independent shreds. Integration requires exact-head Product CI and independent Robot QA on the same candidate SHA. Product `main`, production writes, credentials, sensitive auth/RLS, fiscal actions, purchase orders and irreversible migrations remain gated.

## Coordination contract

`razzo/state/global-lease.json` is the canonical global lease record. A trigger must acquire it with compare-and-swap semantics before creating product work. Exactly one contender may win; stale writers fail closed. The latest lease was released normally after the protected wave found no safe ready product capability.

## Last heartbeat

- **Cell:** `RAZZO-Cell-00`
- **State:** `BLOCKED`
- **Run:** `RAZZO-Cell-00-20260803T212134Z`
- **Observed:** `2026-08-03T21:24:00Z`
- **Message:** All three enabled project task graphs contain only completed work or explicit human-gated work. No artificial capability, product branch or PR was created.

## Current human gates

- Project Giovanni: persisted user-data write.
- PFarma Cloud: purchase-order / destructive production write.
- Family Cloud: irreplaceable-data storage repair execution.

> Machine-readable status: `razzo/state/factory-status.json`.
> Machine-readable lease: `razzo/state/global-lease.json`.
