#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")


def fail(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        fail(f"invalid JSON: {path}: {exc}")
    if not isinstance(value, dict):
        fail(f"JSON object required: {path}")
    return value


def certify(receipts_dir: Path, evidence_path: Path, output_path: Path) -> dict:
    evidence = load_json(evidence_path)
    if evidence.get("schema") != "razzo.homo-novus.phase4-evidence.v1":
        fail("invalid evidence schema")
    generation_id = evidence.get("generation_id")
    project_id = evidence.get("project_id")
    source_repository = evidence.get("source_repository")
    source_sha = evidence.get("source_exact_sha")
    expected = evidence.get("items")
    if not all(isinstance(v, str) and v for v in (generation_id, project_id, source_repository)):
        fail("missing evidence identity")
    if not isinstance(source_sha, str) or not SHA40.fullmatch(source_sha):
        fail("invalid source exact SHA")
    if not isinstance(expected, list) or not expected:
        fail("evidence items required")

    files = sorted(receipts_dir.glob("*.json"))
    if len(files) != len(expected):
        fail(f"receipt count mismatch: {len(files)} != {len(expected)}")

    expected_by_execution: dict[str, dict] = {}
    for item in expected:
        if not isinstance(item, dict):
            fail("invalid evidence item")
        execution_id = item.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id:
            fail("missing evidence execution_id")
        if execution_id in expected_by_execution:
            fail(f"duplicate evidence execution_id: {execution_id}")
        if item.get("run_conclusion") != "success":
            fail(f"run not successful: {execution_id}")
        if not isinstance(item.get("run_id"), int) or not isinstance(item.get("artifact_id"), int):
            fail(f"invalid run/artifact id: {execution_id}")
        digest = item.get("artifact_digest")
        if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            fail(f"invalid artifact digest: {execution_id}")
        expected_by_execution[execution_id] = item

    outputs = []
    seen_work: set[str] = set()
    seen_domains: set[str] = set()
    seen_idempotency: set[str] = set()
    seen_shards: set[str] = set()

    for path in files:
        receipt = load_json(path)
        execution_id = receipt.get("execution_id")
        item = expected_by_execution.get(execution_id)
        if item is None:
            fail(f"unexpected receipt execution_id: {execution_id}")
        required = {
            "schema", "status", "verification_state", "execution_id", "work_item_id",
            "project_id", "generation_id", "source_repository", "input_sha", "target_path",
            "output_sha256", "collision_domain", "idempotency_key", "shard_repository",
            "worker_sha", "product_progress",
        }
        if required - set(receipt):
            fail(f"missing receipt fields: {path.name}")
        if receipt["schema"] != "razzo.homo-novus.phase4-receipt.v1":
            fail(f"invalid receipt schema: {path.name}")
        if receipt["status"] != "HEALTHY" or receipt["verification_state"] != "REAL_WORK_EXACT_REF_VERIFIED":
            fail(f"unverified receipt: {path.name}")
        if receipt["product_progress"] is not False:
            fail(f"unexpected product progress claim: {path.name}")
        if receipt["project_id"] != project_id or receipt["generation_id"] != generation_id:
            fail(f"mixed project/generation: {path.name}")
        if receipt["source_repository"] != source_repository or receipt["input_sha"] != source_sha:
            fail(f"source mismatch: {path.name}")
        if receipt["worker_sha"] != item.get("worker_sha") or receipt["shard_repository"] != item.get("shard_repository"):
            fail(f"worker evidence mismatch: {path.name}")
        if not SHA40.fullmatch(str(receipt["worker_sha"])) or not SHA64.fullmatch(str(receipt["output_sha256"])):
            fail(f"invalid receipt digest: {path.name}")
        if receipt["work_item_id"] in seen_work or receipt["collision_domain"] in seen_domains or receipt["idempotency_key"] in seen_idempotency or receipt["shard_repository"] in seen_shards:
            fail(f"duplicate receipt identity: {path.name}")
        seen_work.add(receipt["work_item_id"])
        seen_domains.add(receipt["collision_domain"])
        seen_idempotency.add(receipt["idempotency_key"])
        seen_shards.add(receipt["shard_repository"])
        outputs.append({
            "work_item_id": receipt["work_item_id"],
            "execution_id": execution_id,
            "shard_repository": receipt["shard_repository"],
            "worker_sha": receipt["worker_sha"],
            "input_sha": receipt["input_sha"],
            "target_path": receipt["target_path"],
            "output_sha256": receipt["output_sha256"],
            "collision_domain": receipt["collision_domain"],
            "idempotency_key": receipt["idempotency_key"],
            "run_id": item["run_id"],
            "artifact_id": item["artifact_id"],
            "artifact_digest": item["artifact_digest"],
        })

    outputs.sort(key=lambda row: row["work_item_id"])
    canonical = json.dumps(outputs, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    composition_sha256 = hashlib.sha256(canonical).hexdigest()
    manifest = {
        "schema": "razzo.homo-novus.phase4-composition.v1",
        "project_id": project_id,
        "generation_id": generation_id,
        "source_repository": source_repository,
        "source_exact_sha": source_sha,
        "verification_state": "REAL_GENERATION_COMPOSED",
        "work_item_count": len(outputs),
        "successful_run_count": len(outputs),
        "receipt_count": len(outputs),
        "shard_count": len(seen_shards),
        "composition_sha256": composition_sha256,
        "product_progress": False,
        "outputs": outputs,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = certify(args.receipts, args.evidence, args.output)
    print(json.dumps({"verification_state": manifest["verification_state"], "composition_sha256": manifest["composition_sha256"], "receipt_count": manifest["receipt_count"]}, sort_keys=True))


if __name__ == "__main__":
    main()
