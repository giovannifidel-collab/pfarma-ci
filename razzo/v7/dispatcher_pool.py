from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MAX_GENERIC_DISPATCHERS = 100


@dataclass(frozen=True)
class DispatcherLease:
    shard_id: str
    dispatcher_id: str
    work_item: dict[str, Any]
    lease_digest: str

    def enveloped_item(self) -> dict[str, Any]:
        item = dict(self.work_item)
        item.update({"shard_id": self.shard_id, "dispatcher_id": self.dispatcher_id,
                     "dispatcher_lease_digest": self.lease_digest, "lease_digest": self.lease_digest})
        return item

    def to_matrix_entry(self) -> dict[str, Any]:
        return {"shard_id": self.shard_id, "dispatcher_id": self.dispatcher_id, "work_count": 1,
                "items_json": json.dumps([self.enveloped_item()], separators=(",", ":")),
                "lease_digest": self.lease_digest}


def available_product_shards() -> list[str]:
    payload = json.loads((ROOT / "razzo" / "v7" / "shards.json").read_text(encoding="utf-8"))
    return [s["shard_id"] for s in payload["shards"] if s.get("enabled") and s.get("health") == "healthy" and s.get("supported_lane") == "product" and not s.get("current_lease")]


def lease_digest(shard_id: str, dispatcher_id: str, item: dict[str, Any], run_id: str = "${RUN_ID}") -> str:
    payload = {"shard_id": shard_id, "dispatcher_id": dispatcher_id, "work_item_id": item["work_item_id"],
               "project_id": item["project_id"], "collision_domain": item["collision_domain"],
               "exact_input_sha": item["exact_input_sha"], "fingerprint": item["fingerprint"], "run_id": run_id}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def assign_generic_dispatchers(work_items: list[dict[str, Any]], *, provider_cap: int,
                               dispatcher_pool_size: int = MAX_GENERIC_DISPATCHERS,
                               run_id: str = "${RUN_ID}") -> list[DispatcherLease]:
    if provider_cap < 1 or dispatcher_pool_size < 1: raise ValueError("capacity must be >= 1")
    domains = [str(i["collision_domain"]) for i in work_items]
    fingerprints = [str(i["fingerprint"]) for i in work_items]
    issues = [(i["project_id"], i.get("issue_number")) for i in work_items]
    if len(domains) != len(set(domains)): raise ValueError("collision domain duplicated before dispatch")
    if len(fingerprints) != len(set(fingerprints)): raise ValueError("fingerprint duplicated before dispatch")
    if len(issues) != len(set(issues)): raise ValueError("same issue duplicated before dispatch")
    for item in work_items:
        if item.get("actionability_state") != "READY": raise ValueError("non-READY item reached product dispatch")
    shards = available_product_shards()
    active = min(provider_cap, dispatcher_pool_size, len(work_items), len(shards))
    return [DispatcherLease(shards[i], f"dispatcher-{i+1:03d}", item,
                            lease_digest(shards[i], f"dispatcher-{i+1:03d}", item, run_id))
            for i, item in enumerate(work_items[:active])]


def annotate_work_items(work_items: list[dict[str, Any]], *, provider_cap: int,
                        dispatcher_pool_size: int = MAX_GENERIC_DISPATCHERS,
                        run_id: str = "${RUN_ID}") -> tuple[list[dict[str, Any]], list[DispatcherLease]]:
    leases = assign_generic_dispatchers(work_items, provider_cap=provider_cap,
                                        dispatcher_pool_size=dispatcher_pool_size, run_id=run_id)
    return [lease.enveloped_item() for lease in leases], leases


def verify_dispatcher_lease(dispatcher_id: str, items: list[dict[str, Any]], expected_digest: str,
                            shard_id: str | None = None, run_id: str = "${RUN_ID}") -> None:
    if len(items) != 1: raise ValueError("each shard lease must contain exactly one work item")
    item = items[0]; sid = shard_id or item.get("shard_id")
    if not sid: raise ValueError("shard_id missing")
    if item.get("dispatcher_id") != dispatcher_id: raise ValueError("dispatcher envelope mismatch")
    actual = lease_digest(str(sid), dispatcher_id, item, run_id)
    if actual != expected_digest: raise ValueError("dispatcher lease digest mismatch")


def dispatcher_matrix_json(work_items: list[dict[str, Any]], *, provider_cap: int,
                           dispatcher_pool_size: int = MAX_GENERIC_DISPATCHERS,
                           run_id: str = "${RUN_ID}") -> str:
    leases = assign_generic_dispatchers(work_items, provider_cap=provider_cap,
                                        dispatcher_pool_size=dispatcher_pool_size, run_id=run_id)
    return json.dumps({"include": [x.to_matrix_entry() for x in leases]}, separators=(",", ":"))
