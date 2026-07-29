#!/usr/bin/env python3
"""RAZZO Super Factory shard allocator.

Pure control-plane logic: convert discovery + declared 1000-shard universe into
an eligibility snapshot. This module never writes to shard repositories.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

PATTERN = re.compile(r"^razzo-shard-(\d{4})$")


def build_snapshot(discovery: dict[str, Any], capacity: int = 1000) -> dict[str, Any]:
    repos = sorted(set(discovery.get("repositories", [])))
    valid: list[str] = []
    rejected: list[str] = []

    for repo in repos:
        match = PATTERN.fullmatch(repo)
        if not match:
            rejected.append(repo)
            continue
        n = int(match.group(1))
        if 1 <= n <= capacity:
            valid.append(repo)
        else:
            rejected.append(repo)

    materialized = set(valid)
    universe = [f"razzo-shard-{n:04d}" for n in range(1, capacity + 1)]
    missing = [repo for repo in universe if repo not in materialized]

    return {
        "schemaVersion": 1,
        "logicalCapacity": capacity,
        "materializedCount": len(valid),
        "eligibleCount": len(valid),
        "dormantUnmaterializedCount": len(missing),
        "eligible": valid,
        "dormantUnmaterialized": missing,
        "rejected": rejected,
        "dispatchPolicy": {
            "mode": "capacity-aware",
            "allDiscoveredEligible": True,
            "physicalConcurrencyIsNotRepositoryCount": True,
            "requirements": [
                "real-dag-ready-work",
                "collision-domain-lease",
                "exact-sha-input",
                "no-human-gated-action",
                "no-backpressure",
                "available-ci-capacity",
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--capacity", type=int, default=1000)
    args = parser.parse_args()

    discovery = json.loads(Path(args.discovery).read_text(encoding="utf-8"))
    snapshot = build_snapshot(discovery, capacity=args.capacity)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(
        f"materialized={snapshot['materializedCount']} "
        f"eligible={snapshot['eligibleCount']} "
        f"dormant={snapshot['dormantUnmaterializedCount']}"
    )


if __name__ == "__main__":
    main()
