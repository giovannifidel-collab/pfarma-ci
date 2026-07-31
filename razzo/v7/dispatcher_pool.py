from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MAX_DISPATCHERS = 12


@dataclass(frozen=True)
class DispatcherLease:
    shard_id: str
    dispatcher_id: str
    work_item: dict[str, Any]
    lease_digest: str

    def enveloped_item(self) -> dict[str, Any]:
        item = dict(self.work_item)
        item.update(
            {
                "shard_id": self.shard_id,
                "dispatcher_id": self.dispatcher_id,
                "lease_digest": self.lease_digest,
            }
        )
        return item

    def to_matrix_entry(self) -> dict[str, Any]:
        return {
            "shard_id": self.shard_id,
            "dispatcher_id": self.dispatcher_id,
            "work_count": 1,
            "items_json": json.dumps([self.enveloped_item()], separators=(",", ":")),
            "lease_digest": self.lease_digest,
        }


def available_product_shards() -> list[str]:
    payload = json.loads((ROOT / "razzo" / "v7" / "shards.json").read_text(encoding="utf-8"))
    shards = [
        str(shard["shard_id"])
        for shard in payload.get("shards", [])
        if shard.get("enabled")
        and shard.get("health") == "healthy"
        and shard.get("supported_lane") == "product"
        and not shard.get("current_lease")
    ]
    return sorted(shards)


def lease_digest(
    shard_id: str,
    dispatcher_id: str,
    item: dict[str, Any],
    run_id: str,
) -> str:
    payload = {
        "shard_id": shard_id,
        "dispatcher_id": dispatcher_id,
        "work_item_id": item["work_item_id"],
        "project_id": item["project_id"],
        "collision_domain": item["collision_domain"],
        "exact_input_sha": item["exact_input_sha"],
        "fingerprint": item["fingerprint"],
        "run_id": str(run_id),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def assign_dispatchers(
    work_items: list[dict[str, Any]],
    *,
    provider_cap: int,
    run_id: str,
) -> list[DispatcherLease]:
    if provider_cap < 1:
        raise ValueError("provider_cap must be >= 1")
    if not run_id:
        raise ValueError("run_id is required")

    domains = [str(item["collision_domain"]) for item in work_items]
    fingerprints = [str(item["fingerprint"]) for item in work_items]
    issue_keys = [
        (str(item["project_id"]), int(item["issue_number"]))
        for item in work_items
        if item.get("issue_number") is not None
    ]

    if len(domains) != len(set(domains)):
        raise ValueError("collision domain duplicated before dispatch")
    if len(fingerprints) != len(set(fingerprints)):
        raise ValueError("fingerprint duplicated before dispatch")
    if len(issue_keys) != len(set(issue_keys)):
        raise ValueError("same issue duplicated before dispatch")
    if any(item.get("actionability_state") != "READY" for item in work_items):
        raise ValueError("non-READY item reached dispatch")

    shards = available_product_shards()
    active = min(provider_cap, MAX_DISPATCHERS, len(work_items), len(shards))
    leases: list[DispatcherLease] = []
    for index, item in enumerate(work_items[:active]):
        shard_id = shards[index]
        dispatcher_id = f"dispatcher-{index + 1:03d}"
        leases.append(
            DispatcherLease(
                shard_id=shard_id,
                dispatcher_id=dispatcher_id,
                work_item=item,
                lease_digest=lease_digest(shard_id, dispatcher_id, item, run_id),
            )
        )
    return leases


def annotate_work_items(
    work_items: list[dict[str, Any]],
    *,
    provider_cap: int,
    run_id: str,
) -> tuple[list[dict[str, Any]], list[DispatcherLease]]:
    leases = assign_dispatchers(work_items, provider_cap=provider_cap, run_id=run_id)
    return [lease.enveloped_item() for lease in leases], leases


def verify_dispatcher_lease(
    dispatcher_id: str,
    items: list[dict[str, Any]],
    expected_digest: str,
    shard_id: str,
    run_id: str,
) -> None:
    if len(items) != 1:
        raise ValueError("each dispatcher lease must contain exactly one item")
    item = items[0]
    if item.get("dispatcher_id") != dispatcher_id:
        raise ValueError("dispatcher envelope mismatch")
    if item.get("shard_id") != shard_id:
        raise ValueError("shard envelope mismatch")
    actual = lease_digest(shard_id, dispatcher_id, item, run_id)
    if actual != expected_digest or item.get("lease_digest") != expected_digest:
        raise ValueError("lease digest mismatch")
