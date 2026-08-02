from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ObjectiveCandidate:
    project_id: str
    objective_key: str
    title: str
    priority: int
    product_value: int
    risk: int
    collision_domains: tuple[str, ...]
    safe: bool = True

    def __post_init__(self) -> None:
        if not self.project_id or not self.objective_key or not self.title:
            raise ValueError("candidate requires project_id, objective_key and title")
        if not self.collision_domains:
            raise ValueError("candidate requires collision domains")
        if self.priority < 0 or self.product_value < 0 or self.risk < 0:
            raise ValueError("candidate scores must be non-negative")

    @property
    def score(self) -> tuple[int, int, int, str, str]:
        return (
            self.priority,
            self.product_value,
            -self.risk,
            self.project_id,
            self.objective_key,
        )


@dataclass(frozen=True)
class ContinuationDecision:
    action: str
    candidate: ObjectiveCandidate | None
    reason: str


def select_next_objective(
    candidates: Iterable[ObjectiveCandidate],
    *,
    enabled_projects: Iterable[str],
    active_objective_keys: Iterable[str] = (),
    active_collision_domains: Iterable[str] = (),
    recently_served_projects: Iterable[str] = (),
) -> ContinuationDecision:
    enabled = set(enabled_projects)
    active_keys = set(active_objective_keys)
    active_domains = set(active_collision_domains)
    recent = tuple(recently_served_projects)
    recent_rank = {project_id: index for index, project_id in enumerate(reversed(recent))}

    eligible: list[ObjectiveCandidate] = []
    for candidate in candidates:
        if candidate.project_id not in enabled:
            continue
        if not candidate.safe:
            continue
        if candidate.objective_key in active_keys:
            continue
        if active_domains.intersection(candidate.collision_domains):
            continue
        eligible.append(candidate)

    if not eligible:
        return ContinuationDecision("WAIT", None, "no safe non-colliding objective is currently eligible")

    def ordering(candidate: ObjectiveCandidate) -> tuple[int, int, int, int, str, str]:
        fairness_penalty = recent_rank.get(candidate.project_id, -1) + 1
        return (
            candidate.priority,
            candidate.product_value,
            -candidate.risk,
            -fairness_penalty,
            candidate.project_id,
            candidate.objective_key,
        )

    selected = max(eligible, key=ordering)
    return ContinuationDecision(
        "SELECT",
        selected,
        "highest-value safe objective after active-key, collision and fairness filtering",
    )
