# HIVE GitHub Cloud Computer

Experimental transport/computation layer. This branch is not authoritative HIVE source and must not absorb project source.

## Model

GitHub is used as an online stateless workstation:

- repository/commit = durable disk and checkpoint
- branch = isolated writable workspace
- PR/Issue = collaboration room and review stream
- GitHub Actions runner = disposable CPU/RAM/SSD
- artifacts/logs = short-lived execution evidence
- HIVE Cloudflare/Neon = persistent control state

No user-owned computer, localhost service, home server or local GPU is required.

## Security boundary

Private source stays private. A trusted GitHub-hosted runner may check out a private project only at an exact validated SHA using a secret-scoped credential, work ephemerally, return evidence, then delete the checkout.

The public CI repository contains transport logic and sanitized metadata only.

## Zero-first use

Use standard GitHub-hosted runners in this public repository only for legitimate repository automation such as exact-source checkout, build, test, validation, packaging and agent-result verification. Do not turn Actions into a permanent server or continuous generic compute process.

HIVE should trigger compute only when work exists. Persistent waiting belongs in the HIVE control plane, not in an always-running Action.

## Agent flow

```text
HIVE task
  -> cloud AI worker receives task/ref
  -> worker creates isolated project branch/PR
  -> GitHub Actions spins up disposable validation computer
  -> exact commit checked out
  -> tests/build/security checks
  -> evidence returned
  -> GPT/independent agent review
  -> HIVE records handoff/result
  -> merge only after PASS
```

## Kimi flow

Kimi installs `hive-agent-skill/SKILL.md` once in its online agent environment. Thereafter `HIVE SYNC` is the short command for reconstructing work from online GitHub/HIVE state.

If Kimi has cloud GitHub write access, it works directly through branches/PRs. If only read access is available, it still follows the same result envelope and another HIVE worker can apply/review the produced patch. No local bridge is required.

## Status

This branch is a design/test lane only. Existing workflows on `main` remain unchanged.
