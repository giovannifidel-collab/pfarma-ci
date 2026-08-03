from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .capability import CapabilityPlan
from .canonical import ProjectContract, build_canonical_objective
from .runtime import ActivationPolicy, ExecutionMode


@dataclass(frozen=True)
class ShadowReport:
    mode: str
    capability_id: str
    revision_id: str
    completion_ratio: float
    next_wave_id: str | None
    selected_nodes: tuple[str, ...]
    objective_fingerprint: str | None
    objective_branch: str | None
    warnings: tuple[str, ...]
    mutations_performed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analyze_shadow(
    plan: CapabilityPlan,
    *,
    project: ProjectContract,
    completed_node_ids: Iterable[str] = (),
    active_collision_domains: Iterable[str] = (),
    max_workers: int = 5,
) -> ShadowReport:
    policy = ActivationPolicy(
        mode=ExecutionMode.SHADOW,
        provider_eligible=False,
        product_writes_allowed=False,
        merge_allowed=False,
    )
    policy.validate()
    completed = plan.validate_completed(completed_node_ids)
    ratio = plan.completion_ratio(completed)
    wave = plan.next_wave(
        completed_node_ids=completed,
        active_collision_domains=active_collision_domains,
        max_workers=max_workers,
    )
    warnings: list[str] = []
    if wave is None and ratio < 1.0:
        warnings.append("No safe wave is currently materializable; collision or dependency analysis is required.")
    if wave is None:
        return ShadowReport(
            mode=policy.mode.value,
            capability_id=plan.capability_id,
            revision_id=plan.revision_id,
            completion_ratio=ratio,
            next_wave_id=None,
            selected_nodes=(),
            objective_fingerprint=None,
            objective_branch=None,
            warnings=tuple(warnings),
        )

    objective = build_canonical_objective(plan, wave, project)
    if len(objective.shreds) == 1:
        warnings.append("The next wave contains only one shred; no intra-wave parallel speedup is available.")
    return ShadowReport(
        mode=policy.mode.value,
        capability_id=plan.capability_id,
        revision_id=plan.revision_id,
        completion_ratio=ratio,
        next_wave_id=wave.wave_id,
        selected_nodes=wave.node_ids,
        objective_fingerprint=objective.fingerprint,
        objective_branch=objective.branch,
        warnings=tuple(warnings),
    )


def write_shadow_report(report: ShadowReport, output: str | Path) -> None:
    Path(output).write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
