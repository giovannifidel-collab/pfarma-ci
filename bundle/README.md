# PFarma authenticated encrypted CI slots

Only the following **AES-256-GCM / PFARMA_CI_BUNDLE_V2 ciphertext** is allowed in this public directory:

- `pfarma-ci.bundle.json`: original PFarma Cloud encrypted package (its original CI/key remain unchanged).
- `pfarma-social.bundle.json`: separate encrypted PFarma Social package (new key, never reuses the gestionale key).

For PFarma Social the private authoritative repository is `giovannifidel-collab/pfarma-social`, and the public trusted workflow is `.github/workflows/verify-encrypted-social.yml`. The workflow never receives Buffer or Meta tokens. It uses only `PFARMA_SOCIAL_BUNDLE_KEY` in the `pfarma-social-trusted` Actions environment to decrypt in temporary runner storage, run offline tests, and write an **unsecret** validation receipt `receipts/pfarma-social-ci.json`.

No plaintext source, private customer data, database export, `.env`, token, secret, key, certificate, or decrypted artifact may be committed here. No PR or fork receives decryption secrets. Only owner-controlled commits to `main` are eligible for decryption.

The two encrypted packages have separate credentials and CI gates; the original PFarma Cloud pipeline is not rerouted through the Social pipeline.
