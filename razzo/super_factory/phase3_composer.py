#!/usr/bin/env python3
"""HOMO NOVUS phase-3 composition core.

Fail-closed composition of a generation from verified shard execution receipts.
This does not merge product code; it certifies that every queued work item has a
unique completed lease and a valid exact-SHA receipt before emitting a generation
composition manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SHA40 = re.compile(r"^[0-9a-f]{40}$")


def _load(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def compose(queue: dict[str, Any], leases: dict[str, Any], receipts_root: Path) -> dict[str, Any]:
    items = queue.get("items", [])
    lease_rows = leases.get("leases", [])
    by_work: dict[str, dict[str, Any]] = {}
    by_idempotency: set[str] = set()

    for lease in lease_rows:
        if lease.get("state") != "COMPLETED":
            continue
        wid = str(lease.get("work_item_id", ""))
        idem = str(lease.get("idempotency_key", ""))
        if not wid or wid in by_work:
            raise ValueError(f"duplicate or missing completed lease for work item: {wid}")
        if not idem or idem in by_idempotency:
            raise ValueError(f"duplicate or missing idempotency key: {idem}")
        by_work[wid] = lease
        by_idempotency.add(idem)

    outputs: list[dict[str, Any]] = []
    generation_ids: set[str] = set()
    project_ids: set[str] = set()
    collision_domains: set[str] = set()

    for item in items:
        if item.get("state", "QUEUED") not in {"QUEUED", "DISPATCHED", "COMPLETED"}:
            continue
        wid = str(item.get("work_item_id", ""))
        lease = by_work.get(wid)
        if not lease:
            raise ValueError(f"missing completed lease for queued work item: {wid}")
        input_sha = str(item.get("input_sha", ""))
        if not SHA40.fullmatch(input_sha):
            raise ValueError(f"invalid exact input SHA for {wid}")
        if lease.get("idempotency_key") != item.get("idempotency_key"):
            raise ValueError(f"idempotency mismatch for {wid}")
        if lease.get("collision_domain") != item.get("collision_domain"):
            raise ValueError(f"collision-domain mismatch for {wid}")

        receipt_file = receipts_root / str(item["execution_id"]) / f"{item['execution_id']}.json"
        if not receipt_file.exists():
            matches = sorted((receipts_root / str(item["execution_id"])).glob("*.json"))
            if len(matches) != 1:
                raise ValueError(f"receipt missing or ambiguous for {wid}")
            receipt_file = matches[0]
        receipt = json.loads(receipt_file.read_text(encoding="utf-8-sig"))
        if receipt.get("status") != "HEALTHY" or receipt.get("verification_state") != "DISPATCH_ENVELOPE_VERIFIED":
            raise ValueError(f"invalid receipt for {wid}")
        receipt_sha = str(receipt.get("exact_sha", ""))
        if not SHA40.fullmatch(receipt_sha):
            raise ValueError(f"receipt exact SHA missing for {wid}")

        generation_ids.add(str(item["generation_id"]))
        project_ids.add(str(item["project_id"]))
        collision_domains.add(str(item["collision_domain"]))
        outputs.append({
            "work_item_id": wid,
            "execution_id": item["execution_id"],
            "project_id": item["project_id"],
            "generation_id": item["generation_id"],
            "input_sha": input_sha,
            "shard": lease["shard"],
            "run_id": lease.get("run_id"),
            "receipt_exact_sha": receipt_sha,
            "receipt_file": receipt_file.as_posix(),
        })

    if not outputs:
        raise ValueError("no composable work items")
    if len(generation_ids) != 1:
        raise ValueError("composition requires exactly one generation_id")
    if len(project_ids) != 1:
        raise ValueError("composition requires exactly one project_id")
    if len(collision_domains) != len(outputs):
        raise ValueError("collision domains are not unique within generation")

    outputs.sort(key=lambda x: x["work_item_id"])
    canonical = json.dumps(outputs, sort_keys=True, separators=(",", ":")).encode()
    composition_sha = hashlib.sha256(canonical).hexdigest()
    return {
        "schema": "razzo.homo-novus.composition.v1",
        "project_id": next(iter(project_ids)),
        "generation_id": next(iter(generation_ids)),
        "work_item_count": len(outputs),
        "verification_state": "GENERATION_RECEIPTS_COMPOSED",
        "composition_sha256": composition_sha,
        "product_progress": False,
        "outputs": outputs,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--queue", required=True)
    p.add_argument("--leases", required=True)
    p.add_argument("--receipts", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    result = compose(_load(a.queue), _load(a.leases), Path(a.receipts))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"generation={result['generation_id']} composed={result['work_item_count']} sha256={result['composition_sha256']}")


if __name__ == "__main__":
    main()
