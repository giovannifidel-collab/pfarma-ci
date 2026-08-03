# RAZZO Factory Live Status

- **Factory:** `RUNNING`
- **Mode:** `PILOT`
- **Updated:** `2026-08-03T22:06:30Z`
- **Observed control-plane SHA:** `2886a487eacb3c2e1ed3772f52f82ef201f0001c`
- **Enabled cells:** `RAZZO-Cell-00`
- **Active capability:** `none`
- **Global lease:** `FREE`
- **Pilot limits:** `1` capability / `2` shreds
- **Live operations issue:** `#753`

## Active boundary

Only `RAZZO-Cell-00` is authorized. It may handle one capability at a time with at most two independent shreds. Integration requires exact-head Product CI and independent Robot QA on the same candidate SHA. Product `main`, production writes, credentials, sensitive auth/RLS, fiscal actions, purchase orders, EasyFarm mutations and irreversible migrations remain gated.

## Last productive wave

- **Run:** `RAZZO-Cell-00-20260803T220203Z`
- **State:** `INTEGRATED_TO_LANE`
- **Repository:** `giovannifidel-collab/family-cloud`
- **Capability:** bounded browser-local alpha export
- **PR:** `#660`
- **Candidate SHA:** `d04359564b2e5712a25864d960ae2099f5fa09eb`
- **Merge SHA:** `ee9218538a2f34f004d4c0d9c2f5e823ceb5b73a`
- **Product CI:** run `30857311269` — success
- **Robot Collaudatore:** run `30857311488` — success

## Discovery outcome

The wave inspected all enabled products and selected the highest-value independent safe candidate:

- Project Giovanni: progress-assessment explanation/export refinement; safe but lower incremental value after the newly integrated deterministic assessment.
- PFarma Cloud: batch recall evaluation preview; useful but overlapping the newly integrated recall-guard domain.
- Family Cloud: local alpha backup export; selected because it is user-visible, browser-local, reversible and independent of the gated repair execution.

## Current human gates

- Project Giovanni: persisted user-data write.
- PFarma Cloud: purchase-order / destructive production write and EasyFarm mutation.
- Family Cloud: irreplaceable-data storage repair execution.

> Machine-readable status: `razzo/state/factory-status.json`.
> Machine-readable lease: `razzo/state/global-lease.json`.
