#!/usr/bin/env python3
"""Fail-closed validator for the canonical RAZZO Robot QA contract."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "razzo" / "robot-qa-policy.json"
CATALOG = ROOT / "razzo" / "robot-missions" / "pfarma-mc04.json"
REQUIRED_LEVELS = {"delta", "fullMacrocycleRegression", "postMergeReplay"}
REQUIRED_FIELDS = {
    "mission_id", "title", "persona", "preconditions", "actions",
    "expected_results", "database_assertions", "audit_assertions",
    "persistence_assertions", "priority", "status"
}

def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)

def validate() -> None:
    policy = load(POLICY)
    catalog = load(CATALOG)
    require(policy.get("schema") == "razzo.robot-qa-policy.v1", "invalid Robot QA policy schema")
    require(policy.get("publicExecutionFabricOnly") is True, "Robot QA must use public execution fabric")
    require(set(policy.get("levels", {})) == REQUIRED_LEVELS, "all three Robot levels are required")
    require(policy.get("truthRules", {}).get("noFakeCanariesAsProductProgress") is True, "fake canaries must be rejected")
    require(catalog.get("projectId") == "pfarma-cloud", "catalog project must be pfarma-cloud")
    require(catalog.get("macrocycleId") == "MC-04", "catalog must target active PFarma MC-04")
    missions = catalog.get("missions")
    require(isinstance(missions, list) and missions, "mission catalog cannot be empty")
    ids = []
    for mission in missions:
        require(isinstance(mission, dict), "mission entries must be objects")
        require(REQUIRED_FIELDS <= set(mission), f"mission missing fields: {mission.get('mission_id')}")
        require(mission["status"] == "PLANNED", "unevidenced mission cannot be marked executed or passed")
        require(mission["priority"] in {"P0", "P1", "P2"}, "invalid mission priority")
        ids.append(mission["mission_id"])
    require(len(ids) == len(set(ids)), "duplicate mission IDs")

if __name__ == "__main__":
    try:
        validate()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"RAZZO Robot QA validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print("RAZZO Robot QA validation passed")
