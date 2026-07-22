# PFarma CI

Public CI transport repository for PFarma Cloud.

## Security boundary

This repository must never contain plaintext PFarma source, EasyFarm data, credentials, `.env` files, private keys, or production exports.

The authoritative application repository remains private. Source payloads admitted here must be authenticated ciphertext produced by the PFarma bundle tool. Decryption is permitted only inside trusted GitHub-hosted workflow runs using the repository secret `PFARMA_CI_BUNDLE_KEY`.

Public forks and pull requests must not receive decryption secrets. Real-source workflows therefore run only from trusted owner-controlled events and never use `pull_request_target`.

## Layout

- `tools/public_ci_bundle.py` — AES-256-GCM pack/unpack utility.
- `tools/test_public_ci_bundle.py` — cryptographic transport regression contract using dummy source only.
- `.github/workflows/bootstrap.yml` — public, secret-free proof on `ubuntu-latest`.
- `.github/workflows/run-encrypted-pfarma.yml` — trusted real-bundle execution entrypoint; fail-closed until the secret and bundle exist.
- `bundle/pfarma-ci.bundle.json` — future encrypted PFarma source payload only; never plaintext.

## Status

Bootstrap phase. No real PFarma source is present in this repository yet. The public-boundary and authenticated-transport contracts are validated on every pull request before encrypted-source activation.
