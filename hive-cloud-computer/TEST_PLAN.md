# HIVE Cloud Computer — Test Plan

This file exists only on the isolated `hive-cloud-computer-v0` branch.

Acceptance criteria for the first cloud-only workstation proof:

1. A GitHub-hosted Ubuntu runner starts from a pull request event.
2. The runner receives the trusted private-source credential only from the protected GitHub environment.
3. It checks out an allow-listed private HIVE project at one exact immutable commit SHA.
4. The checked-out SHA is independently verified before any project commands run.
5. Node dependencies are installed with lifecycle scripts disabled for the pilot.
6. Typecheck and tests execute if present.
7. A short-lived evidence artifact is produced.
8. The private workspace is deleted in an `always()` cleanup step.
9. Nothing is merged into `main` as part of the test.
10. No local computer, local server, or self-hosted runner participates.
