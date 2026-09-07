# Queen public runner

The actual workflow lives at `.github/workflows/hive-queen-public-runner.yml` on `main`. It uses the public repository only as a GitHub-hosted execution plane, checks out an exact pinned commit of the private authoritative HIVE source, executes the existing fail-closed degraded Queen 9-active/1-deferred gate, publishes evidence, and seals only the generated authoritative proof/registry files back to the private repository. Meta remains explicitly deferred.
