# RAZZO Factory Live Status

- **Factory:** `RUNNING`
- **Mode:** `PILOT`
- **Updated:** `2026-08-03T22:52:30Z`
- **Observed control-plane SHA:** `8159928f43a8576a2f73abd31a04ea551f41884f`
- **Enabled cells:** `RAZZO-Cell-00`, `RAZZO-Cell-12`, `RAZZO-Cell-24`, `RAZZO-Cell-36`, `RAZZO-Cell-48`
- **Active capability:** `none`
- **Global lease:** `FREE`
- **Pilot limits:** `1` capability / `3` shreds
- **Live operations issue:** `#753`

## Active boundary

Five staggered trigger cells may attempt work, but the canonical global lease permits only one active capability and one canonical product PR at a time. Integration requires exact-head Product CI and independent Robot QA on the same candidate SHA. Product `main`, production writes, credentials, sensitive auth/RLS, fiscal actions, purchase orders, EasyFarm mutations and irreversible migrations remain gated.

## Last productive wave

- **Run:** `RAZZO-Cell-48-20260803T224837Z`
- **State:** `INTEGRATED_TO_LANE`
- **Repository:** `giovannifidel-collab/family-cloud`
- **Capability:** bounded browser-local alpha backup import preview
- **PR:** `#661`
- **Candidate SHA:** `811b8172d0c4133aa3eb5158447b5f9157d96bbe`
- **Merge SHA:** `3378f8b06a719cff343055e8eae1400a7ed2f434`
- **Product CI:** run `30860144818` — success
- **Robot Collaudatore:** run `30860144798` — success

## Correction applied

The previous dedicated gates failed because the repository has no package lock and the workflows invoked `npm ci`. Cell 48 corrected the same canonical PR without creating duplicates, replaced the dependency installation with Node 22 native type stripping, added syntax and boundary checks, and revalidated the exact candidate head.

## Safety properties

The preview validates the existing `family-cloud.alpha-export.v1` backup schema, enforces a 1 MB file limit and bounded record counts, and performs no import, persistent browser mutation, network request or production write.

## Current human gates

- Project Giovanni: persisted user-data write.
- PFarma Cloud: purchase-order / destructive production write and EasyFarm mutation.
- Family Cloud: irreplaceable-data storage repair execution.

> Machine-readable status: `razzo/state/factory-status.json`.
> Machine-readable lease: `razzo/state/global-lease.json`.
