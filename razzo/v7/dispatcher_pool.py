from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Any, Iterable

MAX_GENERIC_DISPATCHERS = 100


@dataclass(frozen=True)
class DispatcherLease:
    dispatcher_id: str
    work_items: tuple[dict[str, Any], ...]
    lease_digest: str

    def to_matrix_entry(self) -> dict[str, Any]:
        return {
            "dispatcher_id": self.dispatcher_id,
            "work_count": len(self.work_items),
            "items_json": json.dumps(list(self.work_items), separators=(",", ":")),
            "lease_digest": self.lease_digest,
        }


def _lease_digest(dispatcher_id: str, items: Iterable[dict[str, Any]]) -> str:
    payload = {
        "dispatcher_id": dispatcher_id,
        "items": [
            {
                "project_id": item["project_id"],
                "issue_number": int(item["issue_number"]),
                "collision_domain": item["collision_domain"],
                "exact_sha": item["exact_sha"],
            }
            for item in items
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def assign_generic_dispatchers(
    work_items: list[dict[str, Any]],
    *,
    provider_cap: int,
    dispatcher_pool_size: int = MAX_GENERIC_DISPATCHERS,
) -> list[DispatcherLease]:
    """Assign collision-safe work to interchangeable dispatcher lanes.

    Dispatchers are intentionally generic: no project/domain affinity exists.
    The active dispatcher count is bounded by available work, provider capacity,
    and the configured pool size. Work is assigned deterministically round-robin.
    """
    if provider_cap < 1:
        raise ValueError("provider_cap must be >= 1")
    if dispatcher_pool_size < 1:
        raise ValueError("dispatcher_pool_size must be >= 1")

    domains = [str(item["collision_domain"]) for item in work_items]
    if len(domains) != len(set(domains)):
        raise ValueError("collision domain duplicated before dispatch")

    if not work_items:
        return []

    active = min(dispatcher_pool_size, provider_cap, len(work_items))
    buckets: list[list[dict[str, Any]]] = [[] for _ in range(active)]
    for index, item in enumerate(work_items):
        buckets[index % active].append(item)

    leases: list[DispatcherLease] = []
    for index, bucket in enumerate(buckets, start=1):
        dispatcher_id = f"dispatcher-{index:03d}"
        leases.append(
            DispatcherLease(
                dispatcher_id=dispatcher_id,
                work_items=tuple(bucket),
                lease_digest=_lease_digest(dispatcher_id, bucket),
            )
        )
    return leases


def dispatcher_matrix_json(
    work_items: list[dict[str, Any]],
    *,
    provider_cap: int,
    dispatcher_pool_size: int = MAX_GENERIC_DISPATCHERS,
) -> str:
    leases = assign_generic_dispatchers(
        work_items,
        provider_cap=provider_cap,
        dispatcher_pool_size=dispatcher_pool_size,
    )
    return json.dumps({"include": [lease.to_matrix_entry() for lease in leases]}, separators=(",", ":"))
