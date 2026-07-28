from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
    states = [
        ProjectState(
            project_id=project["id"],
            ready=1,
            normal_concurrency=project["normalConcurrency"],
            burst_concurrency=project["burstConcurrency"],
        )
        for project in config["projects"]
    ]
    print(json.dumps(portfolio_decision(states, config["totalNormalSlots"]), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
