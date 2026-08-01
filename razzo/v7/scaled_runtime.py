from __future__ import annotations

"""Compatibility wrapper after rollback of the unsafe expanded topology.

Delegate every command to the proven ten-shard runtime so new waves remain operational.
"""

from razzo.v7.trial_runtime import main


if __name__ == "__main__":
    raise SystemExit(main())
