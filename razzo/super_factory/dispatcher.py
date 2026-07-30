#!/usr/bin/env python3
"""HOMO NOVUS phase-2 dispatcher core.

Pure deterministic control-plane logic. It consumes a verified shard-readiness
snapshot, queued work items, and a persisted lease registry; then emits a
fail-closed dispatch plan. Network dispatch and receipt collection are handled
by the PowerShell executor so the Python core remains testable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHARD = re.compile(r"^razzo-shard-[0-9]{4}$")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_work_item(item: dict[str, Any]) -> None:
    required = {
        "work_item_id", "execution_id", "project_id", "generation_id",
        "input_sha", "collision_domain", "idempotency_key",
    }
    missing = sorted(required - set(item))
    if missing:
        raise ValueError(f"work item missing fields: {', '.join(missing)}")
    if not SHA40.fullmatch(str(item["input_sha"])):
        raise ValueError("input_sha must be an exact lowercase 40-character SHA")
    for key in required - {"input_sha"}:
        if not isinstance(item[key], str) or not item[key].strip():
            raise ValueError(f"{key} must be a non-empty string")


def ready_shards(snapshot: dict[str, Any]) -> list[str]:
    rows = snapshot.get("shards", [])
    result: list[str] = []
    for row in rows:
        name = row.get("shard")
        if row.get("state") != "READY" or not isinstance(name, str) or not SHARD.fullmatch(name):
            continue
        if not SHA40.fullmatch(str(row.get("activation_sha", ""))):
            continue
        if not row.get("artifact_id"):
            continue
        result.append(name)
    return sorted(set(result))


def active_leases(leases: dict[str, Any], now: datetime) -> dict[str, dict[str, Any]]:
    active: dict[str, dict[str, Any]] = {}
    for lease in leases.get("leases", []):
        try:
            expires = parse_time(lease["expires_at"])
            shard = lease["shard"]
        except (KeyError, TypeError, ValueError):
            continue
        if expires > now and isinstance(shard, str):
            active[shard] = lease
    return active


def choose_shard(item: dict[str, Any], candidates: list[str]) -> str:
    if not candidates:
        raise ValueError("no READY shard without an active lease")
    seed = f"{item['collision_domain']}:{item['idempotency_key']}".encode()
    index = int(hashlib.sha256(seed).hexdigest(), 16) % len(candidates)
    return candidates[index]


def build_plan(
    readiness: dict[str, Any],
    queue: dict[str, Any],
    leases: dict[str, Any],
    *,
    now: datetime | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    now = now or utc_now()
    ready = ready_shards(readiness)
    leased = active_leases(leases, now)
    available = [name for name in ready if name not in leased]
    seen_ids = {str(x.get("idempotency_key")) for x in leases.get("leases", [])}
    dispatches: list[dict[str, Any]] = []

    for item in queue.get("items", []):
        if len(dispatches) >= limit or not available:
            break
        if item.get("state", "QUEUED") != "QUEUED":
            continue
        validate_work_item(item)
        if item["idempotency_key"] in seen_ids:
            continue
        shard = choose_shard(item, available)
        available.remove(shard)
        seen_ids.add(item["idempotency_key"])
        dispatches.append({
            "shard": shard,
            "repository": f"giovannifidel-collab/{shard}",
            "workflow": "razzo-shard-worker.yml",
            "inputs": {key: item[key] for key in (
                "execution_id", "work_item_id", "project_id", "generation_id",
                "input_sha", "collision_domain", "idempotency_key",
            )},
        })

    return {
        "schema": "razzo.homo-novus.dispatch-plan.v1",
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "ready_count": len(ready),
        "leased_count": len(leased),
        "available_count_after_plan": len(available),
        "dispatch_count": len(dispatches),
        "dispatches": dispatches,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readiness", required=True)
    parser.add_argument("--queue", required=True)
    parser.add_argument("--leases", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    load = lambda p: json.loads(Path(p).read_text(encoding="utf-8-sig"))
    plan = build_plan(load(args.readiness), load(args.queue), load(args.leases), limit=args.limit)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"ready={plan['ready_count']} dispatches={plan['dispatch_count']}")


if __name__ == "__main__":
    main()
