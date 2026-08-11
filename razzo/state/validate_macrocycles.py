#!/usr/bin/env python3
"""Fail-closed validator for the terminal 60/60 roadmap and rolling Perfection roadmap."""
from __future__ import annotations
import json, re, sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ROADMAP = ROOT / "razzo" / "macrocycles.json"
STATE = ROOT / "razzo" / "macrocycle-state.json"
POLICY = ROOT / "razzo" / "macrocycle-policy.json"
CERTIFIED_HEADS = ROOT / "razzo" / "terminal-certified-heads.json"
PERFECTION_STATE = ROOT / "razzo" / "state" / "perfection-v1.json"
EXPECTED_PROJECTS = {"project-giovanni", "pfarma-cloud", "family-cloud"}
EXPECTED_IDS = {f"MC-{index:02d}" for index in range(1, 21)}
ACTIVE_STATES = {"PLANNED", "ACTIVE", "VERIFYING"}
ALLOWED_STATES = ACTIVE_STATES | {"COMPLETED", "DEFERRED_HUMAN_GATE"}
CRITERION_STATES = {"MISSING", "VERIFIED", "BLOCKED_BY_TRUE_HUMAN_GATE"}
PERFECTION_PROJECTS = {
    "project-giovanni": ("PG", "integration/razzo"),
    "pfarma-cloud": ("PF", "integration/razzo"),
    "family-cloud": ("FC", "agent/bootstrap-family-cloud"),
}
PERFECTION_REQUIRED_CLOSURE = {
    "exactShaProductCi",
    "canonicalIntegration",
    "postMergeOrEquivalentReplay",
    "productSpecificQaWhenDeclared",
    "noKnownUnresolvedBlocker",
}

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

def exact_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(ch in "0123456789abcdef" for ch in value)

def receipt_path(value: object) -> Path:
    require(isinstance(value, str) and value.startswith("receipts/") and ".." not in value, "receipt path must stay under receipts/")
    path = (ROOT / value).resolve()
    require(path.is_relative_to((ROOT / "receipts").resolve()), "receipt path escapes receipts/")
    require(path.is_file(), f"missing persisted receipt: {value}")
    return path

def validate_criteria(project_id: str, criteria: Any) -> list[str]:
    require(isinstance(criteria, list) and criteria, f"{project_id}: macrocycle needs exit criteria")
    ids: list[str] = []
    for criterion in criteria:
        require(isinstance(criterion, dict), f"{project_id}: exit criterion must be an object")
        require(bool(criterion.get("id")), f"{project_id}: exit criterion ID is required")
        require(bool(criterion.get("description")), f"{project_id}: exit criterion description is required")
        require(criterion.get("status") in CRITERION_STATES, f"{project_id}/{criterion.get('id')}: invalid criterion status")
        ids.append(criterion["id"])
    require(len(ids) == len(set(ids)), f"{project_id}: duplicate exit criterion IDs")
    return ids

def validate_completed(project_id: str, completed: Any) -> set[str]:
    require(isinstance(completed, list), f"{project_id}: completed must be a list")
    ids: list[str] = []
    for item in completed:
        require(isinstance(item, dict), f"{project_id}: completed entry must be an object")
        mid = item.get("id")
        require(mid in EXPECTED_IDS, f"{project_id}: completed macrocycle ID is invalid")
        require(item.get("status") == "COMPLETED", f"{project_id}/{mid}: completed status is invalid")
        receipt_path(item.get("receipt"))
        ids.append(mid)
    require(len(ids) == len(set(ids)), f"{project_id}: duplicate completed macrocycle IDs")
    return set(ids)

def validate_pending(project_id: str, pending: Any, completed_ids: set[str], active_id: str | None) -> set[str]:
    require(isinstance(pending, list), f"{project_id}: pendingHumanGates must be a list")
    macro_ids: set[str] = set()
    gate_ids: set[str] = set()
    for gate in pending:
        require(isinstance(gate, dict), f"{project_id}: pending human gate must be an object")
        require(gate.get("macrocycle") in EXPECTED_IDS, f"{project_id}: pending gate macrocycle is invalid")
        require(gate.get("status") == "DEFERRED_HUMAN_GATE", f"{project_id}/{gate.get('macrocycle')}: pending gate must be DEFERRED_HUMAN_GATE")
        for key in ("criterionId", "humanAction", "dependencyScope"):
            require(bool(gate.get(key)), f"{project_id}: pending gate {key} is required")
        require(gate.get("macrocycle") not in completed_ids, f"{project_id}/{gate.get('macrocycle')}: completed macrocycle cannot remain human-gated")
        if active_id is not None:
            require(gate.get("macrocycle") != active_id, f"{project_id}/{gate.get('macrocycle')}: deferred human-gated macrocycle cannot remain execution cursor")
        gate_key = f"{gate.get('macrocycle')}:{gate.get('criterionId')}"
        require(gate_key not in gate_ids, f"{project_id}: duplicate pending human gate {gate_key}")
        gate_ids.add(gate_key)
        macro_ids.add(gate["macrocycle"])
    return macro_ids

def validate_terminal_evidence(state: dict[str, Any]) -> None:
    snapshot = load_json(CERTIFIED_HEADS)
    heads = snapshot.get("projects")
    require(snapshot.get("semantics") == "IMMUTABLE_AUDIT_SNAPSHOT_NOT_LIVE_BRANCH_POINTER", "terminal audited-head snapshot semantics are invalid")
    require(isinstance(heads, dict) and set(heads) == EXPECTED_PROJECTS, "terminal audited-head snapshot must cover exactly the product portfolio")
    for project_id, sha in heads.items():
        require(exact_sha(sha), f"{project_id}: audited head must be exact SHA")
    receipt = load_json(receipt_path(state.get("terminalReceipt")))
    projects = receipt.get("projects")
    require(isinstance(projects, dict) and set(projects) == EXPECTED_PROJECTS, "terminal receipt must cover exactly the product portfolio")
    require(bool(receipt.get("evidenceScope")), "terminal receipt must declare evidenceScope")
    require(receipt.get("certification") == "ROADMAP_COMPLETE_AUDITED_HEADS", "terminal receipt certification semantics are stale")
    require(receipt.get("auditReplay", {}).get("runId") == snapshot.get("auditReplayRunId"), "terminal receipt and audited snapshot must reference the same replay")
    state_by_id = {p.get("id"): p for p in state.get("projects", []) if isinstance(p, dict)}
    for project_id, sha in heads.items():
        entry = projects.get(project_id)
        require(isinstance(entry, dict), f"{project_id}: terminal receipt project entry is required")
        require(entry.get("auditedHead") == sha, f"{project_id}: terminal receipt head does not match audited snapshot")
        require(state_by_id.get(project_id, {}).get("completedThrough") == "MC-20", f"{project_id}: audited terminal project must complete through MC-20")

def validate_perfection_receipt(project_id: str, cycle_id: str, lane: str, receipt: dict[str, Any]) -> None:
    prefix, expected_lane = PERFECTION_PROJECTS[project_id]
    cycle_match = re.fullmatch(rf"{prefix}-(P\d{{2}})", cycle_id)
    require(cycle_match is not None, f"{project_id}: invalid Perfection cycle ID {cycle_id}")
    cycle_suffix = cycle_match.group(1)
    require(receipt.get("schema") == "razzo.perfection-cycle-receipt.v1", f"{project_id}/{cycle_id}: receipt schema mismatch")
    require(receipt.get("roadmap") == "PERFECTION_V1", f"{project_id}/{cycle_id}: wrong roadmap receipt")
    require(receipt.get("project") == project_id and receipt.get("cycle") == cycle_id, f"{project_id}/{cycle_id}: receipt identity mismatch")
    require(receipt.get("status") == "COMPLETED", f"{project_id}/{cycle_id}: receipt is not completed")
    require(lane == expected_lane and receipt.get("canonicalLane") == lane, f"{project_id}/{cycle_id}: canonical lane mismatch")
    require(exact_sha(receipt.get("candidateSha")), f"{project_id}/{cycle_id}: candidate SHA is invalid")
    require(exact_sha(receipt.get("integrationSha")), f"{project_id}/{cycle_id}: integration SHA is invalid")
    require(isinstance(receipt.get("productPullRequest"), int) and receipt["productPullRequest"] > 0, f"{project_id}/{cycle_id}: product PR is required")
    require(isinstance(receipt.get("verifierPullRequest"), int) and receipt["verifierPullRequest"] > 0, f"{project_id}/{cycle_id}: verifier PR is required")
    require(receipt.get("noKnownUnresolvedBlocker") is True, f"{project_id}/{cycle_id}: unresolved blocker prevents closure")
    require(receipt.get("immutableEvidence") is True, f"{project_id}/{cycle_id}: evidence must be immutable")
    require(receipt.get("independentReviewerApproval") is False, f"{project_id}/{cycle_id}: independent approval must not be fabricated")
    require(receipt.get("closureCertification") == f"PERFECTION_{cycle_suffix}_COMPLETED", f"{project_id}/{cycle_id}: closure certification mismatch")
    evidence = receipt.get("evidence")
    require(isinstance(evidence, list) and evidence, f"{project_id}/{cycle_id}: evidence is required")
    successful_kinds: set[str] = set()
    for item in evidence:
        require(isinstance(item, dict) and item.get("conclusion") == "success", f"{project_id}/{cycle_id}: all evidence must be successful")
        kind = item.get("kind")
        require(isinstance(kind, str) and kind, f"{project_id}/{cycle_id}: evidence kind is required")
        successful_kinds.add(kind)
        if "runId" in item:
            require(isinstance(item["runId"], int) and item["runId"] > 0, f"{project_id}/{cycle_id}: evidence runId is invalid")
        if "integrationSha" in item:
            require(item["integrationSha"] == receipt["integrationSha"], f"{project_id}/{cycle_id}: evidence integration SHA mismatch")
    require(any("product-ci" in kind for kind in successful_kinds), f"{project_id}/{cycle_id}: exact-SHA product CI evidence is required")
    qa_required = receipt.get("productSpecificQaRequired")
    require(isinstance(qa_required, bool), f"{project_id}/{cycle_id}: productSpecificQaRequired must be boolean")
    if qa_required:
        qa_kind = receipt.get("productSpecificQaKind")
        require(isinstance(qa_kind, str) and qa_kind in successful_kinds, f"{project_id}/{cycle_id}: required product QA evidence is missing")

def validate_perfection() -> None:
    state = load_json(PERFECTION_STATE)
    require(state.get("schema") == "razzo.perfection-roadmap.v1", "Perfection roadmap schema mismatch")
    require(state.get("roadmap") == "PERFECTION_V1", "Perfection roadmap ID mismatch")
    require(state.get("baseRoadmap") == "COMPLETED_60_OF_60", "Perfection must layer on the immutable 60/60 roadmap")
    require(state.get("historicalTerminalRoadmapUnchanged") is True, "Perfection cannot rewrite historical 60/60 completion")
    status = state.get("status")
    status_match = re.fullmatch(r"P(\d{2})_COMPLETE", status) if isinstance(status, str) else None
    require(status_match is not None, "Perfection rolling closure status is invalid")
    completed_through = int(status_match.group(1))
    require(completed_through >= 1, "Perfection must close at least P01")
    governance = state.get("governance")
    require(isinstance(governance, dict), "Perfection governance is required")
    require(set(governance.get("closureRequires", [])) == PERFECTION_REQUIRED_CLOSURE, "Perfection closure gates are incomplete")
    require(governance.get("independentReviewerApprovalRequired") is False, "Perfection governance review semantics changed unexpectedly")
    projects = state.get("projects")
    require(isinstance(projects, dict) and set(projects) == EXPECTED_PROJECTS, "Perfection project set must match the product portfolio")
    completed_count = 0
    for project_id, project in projects.items():
        require(isinstance(project, dict), f"{project_id}: Perfection project entry is invalid")
        prefix, lane = PERFECTION_PROJECTS[project_id]
        require(project.get("lane") == lane, f"{project_id}: Perfection lane mismatch")
        require(project.get("active") is None and project.get("next") is None, f"{project_id}: closed Perfection ledger must not invent an active/next cycle")
        completed = project.get("completed")
        require(isinstance(completed, list) and len(completed) == completed_through, f"{project_id}: Perfection ledger must be gapless through P{completed_through:02d}")
        for index, item in enumerate(completed, start=1):
            require(isinstance(item, dict), f"{project_id}: Perfection completion entry is invalid")
            expected_cycle = f"{prefix}-P{index:02d}"
            cycle_id = item.get("id")
            require(cycle_id == expected_cycle, f"{project_id}: expected sequential Perfection closure {expected_cycle}")
            require(item.get("status") == "COMPLETED", f"{project_id}/{cycle_id}: completion status mismatch")
            receipt = load_json(receipt_path(item.get("receipt")))
            validate_perfection_receipt(project_id, cycle_id, lane, receipt)
            completed_count += 1
    expected_total = completed_through * len(EXPECTED_PROJECTS)
    require(state.get("completedMacrocycles") == completed_count == expected_total, f"Perfection P{completed_through:02d} portfolio must close exactly {expected_total} macrocycles")
    require(state.get("pendingHumanGates") == [], "Perfection closed portfolio cannot retain pending human gates")

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
    require(isinstance(projects, dict) and set(projects) == EXPECTED_PROJECTS, "roadmap project set does not match enabled product portfolio")
    for pid, project in projects.items():
        require(project.get("productiveMacrocycles") == 20, f"{pid}: productiveMacrocycles must be 20")
        cycles = project.get("macrocycles")
        require(isinstance(cycles, list) and len(cycles) == 20, f"{pid}: expected exactly 20 productive macrocycles")
        require({x.get("id") for x in cycles if isinstance(x, dict)} == EXPECTED_IDS, f"{pid}: IDs must be MC-01 through MC-20 exactly once")
        for item in cycles:
            require(isinstance(item, dict) and bool(item.get("title")) and bool(item.get("outcome")), f"{pid}: macrocycle title/outcome is required")
    state_projects = state.get("projects")
    require(isinstance(state_projects, list), "state projects must be a list")
    require({x.get("id") for x in state_projects if isinstance(x, dict)} == EXPECTED_PROJECTS, "state project set does not match enabled product portfolio")
    terminal_projects = 0
    for project in state_projects:
        pid = project.get("id")
        require(project.get("productiveMacrocycles") == 20, f"{pid}: state must declare 20 productive macrocycles")
        completed_ids = validate_completed(pid, project.get("completed"))
        terminal = project.get("terminal") is True
        if terminal:
            terminal_projects += 1
            require(project.get("active") is None, f"{pid}: terminal project cannot retain an active macrocycle")
            require(project.get("next") is None, f"{pid}: terminal project cannot have a next macrocycle")
            require(project.get("productiveMacrocyclesCompleted") == 20, f"{pid}: terminal project must declare 20/20 completion")
            require(project.get("completedThrough") == "MC-20", f"{pid}: terminal project must complete through MC-20")
            require("MC-20" in completed_ids, f"{pid}: terminal project must persist MC-20 completion")
            receipt_path(project.get("terminalReceipt"))
            require(not validate_pending(pid, project.get("pendingHumanGates", []), completed_ids, None), f"{pid}: terminal project cannot retain pending human gates")
            continue
        active = project.get("active")
        require(isinstance(active, dict), f"{pid}: exactly one execution-cursor macrocycle is required unless terminal")
        require(active.get("id") in EXPECTED_IDS and active.get("status") in ACTIVE_STATES, f"{pid}: active macrocycle is invalid")
        validate_criteria(pid, active.get("exitCriteria"))
        require(active.get("id") not in completed_ids, f"{pid}: active macrocycle is also marked completed")
        pending = validate_pending(pid, project.get("pendingHumanGates", []), completed_ids, active.get("id"))
        idx = int(active["id"].split("-")[1])
        for deferred in pending:
            require(int(deferred.split("-")[1]) < idx, f"{pid}/{deferred}: deferred human gate must be behind execution cursor {active['id']}")
    if state.get("terminal") is True:
        require(terminal_projects == len(EXPECTED_PROJECTS), "terminal portfolio requires every project to be terminal")
        require(state.get("completedProductiveMacrocycles") == 60, "terminal portfolio must declare 60/60 productive macrocycles")
        validate_terminal_evidence(state)
    else:
        require(terminal_projects == 0, "mixed terminal/non-terminal portfolio state is forbidden")
    validate_perfection()

if __name__ == "__main__":
    try:
        validate()
    except ValueError as exc:
        print(f"RAZZO macrocycle validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print("RAZZO macrocycle validation passed: historical 60/60 + rolling Perfection v1")
