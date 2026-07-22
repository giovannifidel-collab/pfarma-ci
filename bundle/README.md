# Encrypted bundle slot

Only `pfarma-ci.bundle.json` is permitted here.

It must be an authenticated `PFARMA_CI_BUNDLE_V2` / AES-256-GCM envelope produced from the private PFarma source repository. No plaintext source, database export, `.env`, credential, key, certificate, EasyFarm file, or decrypted artifact may ever be committed here.
