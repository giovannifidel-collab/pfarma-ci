# Bootstrap Kimi into HIVE

Purpose: one-time setup for Kimi to join HIVE as an online coding/review worker without localhost or user-owned runtime hardware.

## Canonical Skill

Read and adopt the Skill at:

`hive-agent-skill/SKILL.md`

from repository:

`giovannifidel-collab/pfarma-ci`

branch:

`hive-cloud-computer-v0`

Create/enable a reusable custom Skill named `hive-agent` using that document as the authoritative operating contract. Do not rewrite or weaken its security, isolation, zero-first, exact-SHA, branch/PR, or structured-result rules.

If GitHub access is available, connect/authorize it using the user's normal Kimi/GitHub authorization flow. Never ask the user to paste GitHub tokens into chat.

After setup, when the user says `HIVE SYNC`:

1. inspect the HIVE task source identified by the user or the current GitHub context;
2. follow the `hive-agent` Skill;
3. work only on the exact assigned repository/ref and isolated branch;
4. create a PR when requested/available;
5. return the HIVE Result Envelope;
6. hand off to GPT when independent review is required.

## First certification task

The first certification task is GitHub issue `HIVE-KIMI-0001` in `giovannifidel-collab/pfarma-ci`.

For that task only, base work on branch `hive-cloud-computer-v0`; never target `main`.

When the Skill is active and GitHub access is ready, report exactly:

`HIVE READY`
