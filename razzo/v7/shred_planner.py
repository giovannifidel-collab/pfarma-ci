from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

OBJECTIVE_ID = "pfarma-interwarehouse-transfer-preview-v1"


def _shred(shred_id: str, role: str, dependencies: list[str], artifact: str) -> dict[str, Any]:
    return {
        "shred_id": shred_id,
        "role": role,
        "dependencies": dependencies,
        "artifact": artifact,
        "collision_domain": f"{OBJECTIVE_ID}/{artifact}",
        "idempotency_key": hashlib.sha256(f"{OBJECTIVE_ID}:{shred_id}".encode()).hexdigest()[:20],
    }


def build_plan(*, repository: str, exact_input_sha: str, integration_lane: str) -> dict[str, Any]:
    shreds = [
        _shred("S1-contract", "Define accepted warehouses, quantities and result schema.", [], "contract"),
        _shred("S2-logic", "Define deterministic post-transfer balance logic.", ["S1-contract"], "logic"),
        _shred("S3-safety", "Define read-only invariants and rejection rules.", ["S1-contract"], "safety"),
        _shred("S4-happy-tests", "Define valid transfer regression cases.", ["S1-contract", "S2-logic"], "happy_tests"),
        _shred("S5-error-tests", "Define invalid warehouse and insufficient stock regressions.", ["S1-contract", "S3-safety"], "error_tests"),
        _shred("S6-integrate", "Assemble one module and one focused test file.", ["S2-logic", "S3-safety", "S4-happy-tests", "S5-error-tests"], "integrate"),
    ]
    return {
        "schema": "razzo-shred-plan-v1",
        "objective_id": OBJECTIVE_ID,
        "project_id": "pfarma-cloud",
        "repository": repository,
        "integration_lane": integration_lane,
        "exact_input_sha": exact_input_sha,
        "canonical_branch": f"razzo/shred/{OBJECTIVE_ID}/{exact_input_sha[:12]}",
        "single_publish": True,
        "shreds": shreds,
    }


def validate_plan(plan: dict[str, Any]) -> None:
    shreds = plan["shreds"]
    ids = [item["shred_id"] for item in shreds]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate shred_id")
    keys = [item["idempotency_key"] for item in shreds]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate idempotency_key")
    known = set(ids)
    for item in shreds:
        unknown = set(item["dependencies"]) - known
        if unknown:
            raise ValueError(f"unknown dependencies for {item['shred_id']}: {sorted(unknown)}")
        if item["shred_id"] in item["dependencies"]:
            raise ValueError("self dependency")
    if not plan.get("single_publish"):
        raise ValueError("pilot must publish exactly once")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--exact-input-sha", required=True)
    parser.add_argument("--integration-lane", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    plan = build_plan(repository=args.repository, exact_input_sha=args.exact_input_sha, integration_lane=args.integration_lane)
    validate_plan(plan)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"objective_id": plan["objective_id"], "shreds": len(plan["shreds"]), "single_publish": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
