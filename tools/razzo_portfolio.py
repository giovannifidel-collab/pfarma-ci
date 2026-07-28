from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class ProjectState:
    project_id: str
    ready: int
    backpressure: bool = False
    human_gate: bool = False
    normal_concurrency: int = 1
    burst_concurrency: int = 1

    @property
    def runnable(self) -> int:
        if self.backpressure or self.human_gate:
            return 0
        return max(0, self.ready)


def project_state_from_task_graph(
    project_id: str,
    graph: dict[str, Any],
    *,
    normal_concurrency: int,
    burst_concurrency: int,
    backpressure: bool = False,
) -> ProjectState:
    tasks = graph.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("task graph must contain a tasks list")

    ready = 0
    blocked_human_gate = False
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("task entries must be objects")
        status = task.get("status")
        if status == "ready":
            ready += 1
        if status == "blocked" and (task.get("humanGate") or task.get("human_gate")):
            blocked_human_gate = True

    return ProjectState(
        project_id=project_id,
        ready=ready,
        backpressure=backpressure,
        human_gate=ready == 0 and blocked_human_gate,
        normal_concurrency=normal_concurrency,
        burst_concurrency=burst_concurrency,
    )


def _require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")
    return value


def project_state_from_snapshot(
    project: dict[str, Any], state: dict[str, Any], exact_ref: str
) -> ProjectState:
    project_id = project.get("id")
    if state.get("id") != project_id:
        raise ValueError(f"portfolio state id mismatch for {project_id}")

    snapshot_sha = state.get("exactSha")
    if not isinstance(snapshot_sha, str) or not _SHA_RE.fullmatch(snapshot_sha):
        raise ValueError(f"invalid exactSha for {project_id}")
    if snapshot_sha != exact_ref:
        raise ValueError(f"stale portfolio state for {project_id}: exact SHA mismatch")

    ready = state.get("ready")
    if not isinstance(ready, int) or isinstance(ready, bool) or ready < 0:
        raise ValueError(f"ready must be a non-negative integer for {project_id}")

    normal = project.get("normalConcurrency")
    burst = project.get("burstConcurrency")
    if not isinstance(normal, int) or normal <= 0:
        raise ValueError(f"invalid normalConcurrency for {project_id}")
    if not isinstance(burst, int) or burst < normal:
        raise ValueError(f"invalid burstConcurrency for {project_id}")

    return ProjectState(
        project_id=project_id,
        ready=ready,
        backpressure=_require_bool(state.get("backpressure"), f"backpressure for {project_id}"),
        human_gate=_require_bool(state.get("humanGate"), f"humanGate for {project_id}"),
        normal_concurrency=normal,
        burst_concurrency=burst,
    )


def load_reconciled_states(root: Path, config: dict[str, Any]) -> list[ProjectState]:
    snapshot_path = root / "razzo" / "project-state.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    entries = snapshot.get("projects")
    if not isinstance(entries, list):
        raise ValueError("portfolio state snapshot must contain a projects list")

    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise ValueError("portfolio state entries must be objects with string ids")
        if entry["id"] in by_id:
            raise ValueError(f"duplicate portfolio state id: {entry['id']}")
        by_id[entry["id"]] = entry

    projects = config.get("projects")
    if not isinstance(projects, list):
        raise ValueError("project configuration must contain a projects list")

    states: list[ProjectState] = []
    expected_ids: set[str] = set()
    for project in projects:
        if not isinstance(project, dict) or not isinstance(project.get("id"), str):
            raise ValueError("project configuration entries must have string ids")
        project_id = project["id"]
        expected_ids.add(project_id)
        ref_file = project.get("portfolioRefFile")
        if not isinstance(ref_file, str) or not ref_file:
            raise ValueError(f"portfolioRefFile missing for {project_id}")
        exact_ref = (root / ref_file).read_text(encoding="utf-8").strip()
        if not _SHA_RE.fullmatch(exact_ref):
            raise ValueError(f"canonical ref is not an exact SHA for {project_id}")
        entry = by_id.get(project_id)
        if entry is None:
            raise ValueError(f"portfolio state missing project: {project_id}")
        states.append(project_state_from_snapshot(project, entry, exact_ref))

    extra_ids = set(by_id) - expected_ids
    if extra_ids:
        raise ValueError(f"portfolio state contains unknown projects: {sorted(extra_ids)}")
    return states


def allocate_portfolio(states: list[ProjectState], total_slots: int) -> dict[str, int]:
    allocations = {state.project_id: 0 for state in states}
    healthy = [state for state in states if state.runnable > 0]
    if not healthy or total_slots <= 0:
        return allocations

    remaining = total_slots
    for state in healthy:
        if remaining <= 0:
            break
        allocations[state.project_id] = 1
        remaining -= 1

    while remaining > 0:
        progressed = False
        for state in healthy:
            current = allocations[state.project_id]
            cap = min(state.runnable, state.normal_concurrency)
            if current >= cap:
                continue
            allocations[state.project_id] += 1
            remaining -= 1
            progressed = True
            if remaining == 0:
                break
        if not progressed:
            break
    return allocations


def portfolio_decision(states: list[ProjectState], total_slots: int) -> dict[str, Any]:
    allocation = allocate_portfolio(states, total_slots)
    ready_total = sum(state.ready for state in states)
    runnable_total = sum(state.runnable for state in states)
    used = sum(allocation.values())
    safe_backlog_exhausted = ready_total == 0
    all_ready_work_gated = ready_total > 0 and runnable_total == 0
    self_replan = runnable_total == 0 and (safe_backlog_exhausted or all_ready_work_gated)
    if all_ready_work_gated:
        replan_reason = "all-ready-work-gated"
    elif safe_backlog_exhausted:
        replan_reason = "safe-backlog-exhausted"
    else:
        replan_reason = None
    return {
        "readyTotal": ready_total,
        "runnableTotal": runnable_total,
        "allocated": used,
        "idle": max(0, total_slots - used),
        "allocation": allocation,
        "backpressure": [state.project_id for state in states if state.backpressure],
        "humanGates": [state.project_id for state in states if state.human_gate],
        "safeBacklogExhausted": safe_backlog_exhausted,
        "selfReplan": self_replan,
        "replanReason": replan_reason,
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "razzo" / "projects.json").read_text(encoding="utf-8"))
    states = load_reconciled_states(root, config)
    print(json.dumps(portfolio_decision(states, config["totalNormalSlots"]), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
