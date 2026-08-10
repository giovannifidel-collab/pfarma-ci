#!/usr/bin/env python3
"""Fail-closed validator for RAZZO product macrocycles."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ROADMAP = ROOT / "razzo" / "macrocycles.json"
STATE = ROOT / "razzo" / "macrocycle-state.json"
POLICY = ROOT / "razzo" / "macrocycle-policy.json"
EXPECTED_PROJECTS = {"project-giovanni", "pfarma-cloud", "family-cloud"}
EXPECTED_IDS = {f"MC-{index:02d}" for index in range(1, 21)}
ACTIVE_STATES = {"PLANNED", "ACTIVE", "VERIFYING"}
ALLOWED_STATES = ACTIVE_STATES | {"COMPLETED", "DEFERRED_HUMAN_GATE"}
CRITERION_STATES = {"MISSING", "VERIFIED", "BLOCKED_BY_TRUE_HUMAN_GATE"}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load {path.relative_to(ROOT)}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a JSON object")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_criteria(project_id: str, criteria: Any) -> list[str]:
    require(isinstance(criteria, list) and criteria, f"{project_id}: macrocycle needs exit criteria")
    criterion_ids: list[str] = []
    for criterion in criteria:
        require(isinstance(criterion, dict), f"{project_id}: exit criterion must be an object")
        require(bool(criterion.get("id")), f"{project_id}: exit criterion ID is required")
        require(bool(criterion.get("description")), f"{project_id}: exit criterion description is required")
        require(criterion.get("status") in CRITERION_STATES, f"{project_id}/{criterion.get('id')}: invalid criterion status")
        criterion_ids.append(criterion["id"])
    require(len(criterion_ids) == len(set(criterion_ids)), f"{project_id}: duplicate exit criterion IDs")
    return criterion_ids


def validate_completed(project_id: str, completed: Any) -> set[str]:
    require(isinstance(completed, list), f"{project_id}: completed must be a list")
    ids: list[str] = []
    for item in completed:
        require(isinstance(item, dict), f"{project_id}: completed entry must be an object")
        macrocycle_id = item.get("id")
        require(macrocycle_id in EXPECTED_IDS, f"{project_id}: completed macrocycle ID is invalid")
        require(item.get("status") == "COMPLETED", f"{project_id}/{macrocycle_id}: completed status is invalid")
        require(bool(item.get("receipt")), f"{project_id}/{macrocycle_id}: completed receipt is required")
        ids.append(macrocycle_id)
    require(len(ids) == len(set(ids)), f"{project_id}: duplicate completed macrocycle IDs")
    return set(ids)


def validate_pending(project_id: str, pending: Any, completed_ids: set[str], active_id: str | None) -> set[str]:
    require(isinstance(pending, list), f"{project_id}: pendingHumanGates must be a list")
    pending_macrocycle_ids: set[str] = set()
    pending_gate_ids: set[str] = set()
    for gate in pending:
        require(isinstance(gate, dict), f"{project_id}: pending human gate must be an object")
        require(gate.get("macrocycle") in EXPECTED_IDS, f"{project_id}: pending gate macrocycle is invalid")
        require(gate.get("status") == "DEFERRED_HUMAN_GATE", f"{project_id}/{gate.get('macrocycle')}: pending gate must be DEFERRED_HUMAN_GATE")
        require(bool(gate.get("criterionId")), f"{project_id}: pending gate criterionId is required")
        require(bool(gate.get("humanAction")), f"{project_id}: pending gate humanAction is required")
        require(bool(gate.get("dependencyScope")), f"{project_id}: pending gate dependencyScope is required")
        require(gate.get("macrocycle") not in completed_ids, f"{project_id}/{gate.get('macrocycle')}: completed macrocycle cannot remain human-gated")
        if active_id is not None:
            require(gate.get("macrocycle") != active_id, f"{project_id}/{gate.get('macrocycle')}: deferred human-gated macrocycle cannot remain execution cursor")
        gate_key = f"{gate.get('macrocycle')}:{gate.get('criterionId')}"
        require(gate_key not in pending_gate_ids, f"{project_id}: duplicate pending human gate {gate_key}")
        pending_gate_ids.add(gate_key)
        pending_macrocycle_ids.add(gate["macrocycle"])
    return pending_macrocycle_ids


def validate() -> None:
    policy = load_json(POLICY)
    roadmap = load_json(ROADMAP)
    state = load_json(STATE)

    require(policy.get("productiveMacrocyclesPerProject") == 20, "policy must require 20 productive macrocycles")
    require(policy.get("baselineMacrocycle") == "MC-00", "baseline must be MC-00")
    continuity = policy.get("humanGateContinuity")
    require(isinstance(continuity, dict) and continuity.get("enabled") is True, "humanGateContinuity must be enabled")
    require(policy.get("rules", {}).get("trueHumanGateMustNeverStopScheduler") is True, "true human gates must not stop the scheduler")

    projects = roadmap.get("projects")
    require(isinstance(projects, dict), "roadmap projects must be an object")
    require(set(projects) == EXPECTED_PROJECTS, "roadmap project set does not match enabled product portfolio")
    for project_id, project in projects.items():
        require(project.get("productiveMacrocycles") == 20, f"{project_id}: productiveMacrocycles must be 20")
        macrocycles = project.get("macrocycles")
        require(isinstance(macrocycles, list) and len(macrocycles) == 20, f"{project_id}: expected exactly 20 productive macrocycles")
        ids = {item.get("id") for item in macrocycles if isinstance(item, dict)}
        require(ids == EXPECTED_IDS, f"{project_id}: IDs must be MC-01 through MC-20 exactly once")
        for item in macrocycles:
            require(isinstance(item, dict), f"{project_id}: macrocycle entries must be objects")
            require(bool(item.get("title")), f"{project_id}/{item.get('id')}: title is required")
            require(bool(item.get("outcome")), f"{project_id}/{item.get('id')}: outcome is required")

    state_projects = state.get("projects")
    require(isinstance(state_projects, list), "state projects must be a list")
    require({item.get("id") for item in state_projects if isinstance(item, dict)} == EXPECTED_PROJECTS, "state project set does not match enabled product portfolio")

    terminal_projects = 0
    for project in state_projects:
        project_id = project.get("id")
        require(project.get("productiveMacrocycles") == 20, f"{project_id}: state must declare 20 productive macrocycles")
        completed_ids = validate_completed(project_id, project.get("completed"))
        terminal = project.get("terminal") is True

        if terminal:
            terminal_projects += 1
            require(project.get("active") is None, f"{project_id}: terminal project cannot retain an active macrocycle")
            require(project.get("next") is None, f"{project_id}: terminal project cannot have a next macrocycle")
            require(project.get("productiveMacrocyclesCompleted") == 20, f"{project_id}: terminal project must declare 20/20 completion")
            require(project.get("completedThrough") == "MC-20", f"{project_id}: terminal project must complete through MC-20")
            require("MC-20" in completed_ids, f"{project_id}: terminal project must persist MC-20 completion")
            require(bool(project.get("terminalReceipt")), f"{project_id}: terminal receipt is required")
            pending_ids = validate_pending(project_id, project.get("pendingHumanGates", []), completed_ids, None)
            require(not pending_ids, f"{project_id}: terminal project cannot retain pending human gates")
            continue

        active = project.get("active")
        require(isinstance(active, dict), f"{project_id}: exactly one execution-cursor macrocycle is required unless terminal")
        require(active.get("id") in EXPECTED_IDS, f"{project_id}: active macrocycle ID is invalid")
        require(active.get("status") in ACTIVE_STATES, f"{project_id}: active status is invalid")
        validate_criteria(project_id, active.get("exitCriteria"))
        require(active.get("id") not in completed_ids, f"{project_id}: active macrocycle is also marked completed")
        pending_ids = validate_pending(project_id, project.get("pendingHumanGates", []), completed_ids, active.get("id"))
        active_index = int(active["id"].split("-")[1])
        for deferred_id in pending_ids:
            require(int(deferred_id.split("-")[1]) < active_index, f"{project_id}/{deferred_id}: deferred human gate must be behind execution cursor {active['id']}")

    portfolio_terminal = state.get("terminal") is True
    if portfolio_terminal:
        require(terminal_projects == len(EXPECTED_PROJECTS), "terminal portfolio requires every project to be terminal")
        require(state.get("completedProductiveMacrocycles") == 60, "terminal portfolio must declare 60/60 productive macrocycles")
        require(bool(state.get("terminalReceipt")), "terminal portfolio receipt is required")
    else:
        require(terminal_projects == 0, "mixed terminal/non-terminal portfolio state is forbidden")


if __name__ == "__main__":
    try:
        validate()
    except ValueError as exc:
        print(f"RAZZO macrocycle validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print("RAZZO macrocycle validation passed")
