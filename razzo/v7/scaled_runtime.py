from __future__ import annotations

"""Compatibility wrapper after rollback of the unsafe 8-worker topology.

The workflow may still invoke ``razzo.v7.scaled_runtime`` while active runs drain.
Delegate every command to the proven ten-shard runtime so new waves remain operational.
"""

from razzo.v7.trial_runtime import main


if __name__ == "__main__":
    raise SystemExit(main())
