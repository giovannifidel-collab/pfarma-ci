# Queen vNext public execution policy

For Queen vNext, use the public execution path by default whenever a task can run without exposing private source, credentials, or private project data.

- Public runner/execution repo: `giovannifidel-collab/pfarma-ci`
- Private authority/control plane: `giovannifidel-collab/hive-alveare`
- Queen V1 release locks remain unchanged.
- Public execution must consume only explicit contracts and sanitized inputs.
- Secrets stay in platform secret stores and are never committed.
- Private data must never be copied into the public repository.
- Paid fallback remains disabled by default.
