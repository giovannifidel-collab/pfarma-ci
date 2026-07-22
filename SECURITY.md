# Security policy

`pfarma-ci` is intentionally public but must contain no plaintext PFarma application source or operational data.

## Never commit

- PFarma plaintext source beyond the small public transport/validation tools already allowlisted;
- `.env` files or credentials;
- AES bundle keys or access tokens;
- EasyFarm databases, exports, snapshots, customer/supplier records, fiscal documents or production data;
- decrypted CI workspaces or artifacts.

## Trusted decryption boundary

Real bundle decryption is allowed only in owner-controlled GitHub Actions runs from this repository. The key is expected in `PFARMA_CI_BUNDLE_KEY` and must be stored as an Actions secret. Fork pull requests must never be granted that secret, and `pull_request_target` must not be used for decrypted-source execution.

Any unexpected file is rejected by `tools/validate_public_repo.py` and the bootstrap workflow.
