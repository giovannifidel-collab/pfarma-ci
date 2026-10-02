# HIVE Kimi Cloud Worker

This is the cloud-only path for attaching Kimi Code to HIVE without a local computer.

## Architecture

- GitHub Codespaces is used only for the one-time OAuth bootstrap.
- Kimi Code OAuth state is streamed directly into the encrypted repository secret `HIVE_KIMI_CODE_HOME_B64`.
- GitHub Actions is the disposable cloud computer for recurring Kimi work.
- The worker restores credentials only inside the ephemeral runner, installs the HIVE Agent Skill, runs Kimi Code non-interactively, then deletes the credentials.
- No credential is committed or uploaded as an artifact.

## One-time bootstrap

Open a Codespace from branch `hive-cloud-computer-v0` of `giovannifidel-collab/pfarma-ci`.

The devcontainer installs Kimi Code automatically. In the Codespace terminal run:

```bash
bash hive-kimi-cloud/bootstrap-oauth.sh
```

The script will:

1. start the official `kimi login` OAuth device-code flow;
2. ask the user to authorize Kimi Code in the browser;
3. use GitHub CLI authentication already available in Codespaces when sufficient;
4. otherwise start the official GitHub CLI browser OAuth flow;
5. package only Kimi Code `config.toml` (when present) and `credentials/`;
6. stream the package directly into the encrypted GitHub Actions secret;
7. print completion without revealing the credential.

After success, stop or delete the Codespace.

## Worker test

Run workflow `HIVE Kimi Cloud Worker` on branch `hive-cloud-computer-v0` with:

- `issue_number`: `1165`
- `base_branch`: `hive-cloud-computer-v0`

The worker must create a separate HIVE task branch and PR. The existing `HIVE Kimi Roundtrip Validator` must then validate the PR.

## Security rules

- Never print the Kimi credential bundle.
- Never save OAuth credentials as workflow artifacts or repository files.
- Never use GitHub Actions cache to persist credentials.
- Never run this worker on untrusted pull-request code while secrets are available.
- Never target `main` in v0.
- Keep provider access optional; HIVE must remain operational without Kimi.
