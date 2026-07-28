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
    return {
        "readyTotal": ready_total,
        "runnableTotal": runnable_total,
        "allocated": used,
        "idle": max(0, total_slots - used),
        "allocation": allocation,
        "backpressure": [state.project_id for state in states if state.backpressure],
        "humanGates": [state.project_id for state in states if state.human_gate],
        "selfReplan": ready_total > 0 and runnable_total == 0,
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
