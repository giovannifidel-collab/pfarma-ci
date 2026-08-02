from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .model import DeliveryObjective, ObjectiveState, ShredContract


@dataclass(frozen=True)
class ProjectContract:
    project_id: str
    repository: str
    integration_lane: str
    enabled: bool
    protect_main: bool
    max_builders: int = 5


@dataclass(frozen=True)
class ExistingObjectivePR:
    number: int
    head: str
    base: str
    state: str
    fingerprint: str


@dataclass(frozen=True)
class ControllerDecision:
    action: str
    reason: str
    objective: DeliveryObjective
    existing_pr_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "fingerprint": self.objective.fingerprint,
            "objective_branch": self.objective.branch,
            "project_id": self.objective.project_id,
            "repository": self.objective.repository,
            "integration_lane": self.objective.integration_lane,
            "base_sha": self.objective.base_sha,
            "existing_pr_number": self.existing_pr_number,
            "state": self.objective.state.value,
            "shred_count": len(self.objective.shreds),
        }


def load_projects(path: str | Path) -> dict[str, ProjectContract]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    projects: dict[str, ProjectContract] = {}
    for raw in payload.get("projects", []):
        project_id = str(raw.get("id", "")).strip()
        repository = str(raw.get("repository", "")).strip()
        if not project_id or not repository:
            raise ValueError("every project requires id and repository")
        if project_id in projects:
            raise ValueError(f"duplicate project id: {project_id}")
        configured = int(raw.get("normalConcurrency", 1))
        projects[project_id] = ProjectContract(
            project_id=project_id,
            repository=repository,
            integration_lane=str(raw.get("integrationLane") or "integration/razzo"),
            enabled=bool(raw.get("enabled", True)),
            protect_main=bool(raw.get("protectMain", True)),
            max_builders=max(1, min(5, configured)),
        )
    return projects


def objective_from_payload(
    payload: dict[str, Any],
    *,
    projects: dict[str, ProjectContract],
) -> DeliveryObjective:
    project_id = str(payload.get("project_id", "")).strip()
    if project_id not in projects:
        raise ValueError(f"unknown project_id: {project_id}")
    project = projects[project_id]
    if not project.enabled:
        raise ValueError(f"project is disabled: {project_id}")

    raw_shreds = payload.get("shreds", [])
    if not isinstance(raw_shreds, list):
        raise ValueError("shreds must be a list")
    if len(raw_shreds) > project.max_builders:
        raise ValueError(
            f"objective requests {len(raw_shreds)} shreds but project limit is {project.max_builders}"
        )

    shreds = tuple(
        ShredContract(
            shred_id=str(item["shred_id"]),
            responsibility=str(item["responsibility"]),
            dependencies=tuple(str(x) for x in item.get("dependencies", [])),
            allowed_surfaces=tuple(str(x) for x in item.get("allowed_surfaces", [])),
            acceptance_subset=tuple(str(x) for x in item.get("acceptance_subset", [])),
            collision_domain=str(item["collision_domain"]),
        )
        for item in raw_shreds
    )

    objective = DeliveryObjective(
        project_id=project.project_id,
        repository=project.repository,
        integration_lane=project.integration_lane,
        base_sha=str(payload.get("base_sha", "")),
        goal=str(payload.get("goal", "")),
        user_outcome=str(payload.get("user_outcome", "")),
        acceptance_criteria=tuple(str(x) for x in payload.get("acceptance_criteria", [])),
        collision_domains=tuple(str(x) for x in payload.get("collision_domains", [])),
        state=ObjectiveState.DISCOVERED,
        shreds=shreds,
    )
    objective.validate()
    return objective


def decide(
    objective: DeliveryObjective,
    *,
    existing_prs: Iterable[ExistingObjectivePR] = (),
    live_integration_head: str,
) -> ControllerDecision:
    objective.validate()
    if live_integration_head != objective.base_sha:
        objective.state = ObjectiveState.NEEDS_REPLAN
        return ControllerDecision(
            action="NEEDS_REPLAN",
            reason="integration head moved since objective planning",
            objective=objective,
        )

    matches = [
        pr
        for pr in existing_prs
        if pr.state == "open" and pr.fingerprint == objective.fingerprint
    ]
    if len(matches) > 1:
        objective.state = ObjectiveState.FAILED
        return ControllerDecision(
            action="BLOCKED_DUPLICATE_PR",
            reason="more than one open PR exists for the objective fingerprint",
            objective=objective,
        )
    if matches:
        pr = matches[0]
        if pr.head != objective.branch or pr.base != objective.integration_lane:
            objective.state = ObjectiveState.FAILED
            return ControllerDecision(
                action="BLOCKED_CANONICAL_MISMATCH",
                reason="existing objective PR does not use canonical head/base",
                objective=objective,
                existing_pr_number=pr.number,
            )
        objective.state = ObjectiveState.PLANNED
        return ControllerDecision(
            action="RESUME_EXISTING",
            reason="canonical objective PR already exists",
            objective=objective,
            existing_pr_number=pr.number,
        )

    objective.state = ObjectiveState.PLANNED
    return ControllerDecision(
        action="CREATE_OBJECTIVE_BRANCH",
        reason="no canonical open PR exists for the objective fingerprint",
        objective=objective,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Validate and plan one RAZZO Delivery Objective")
    parser.add_argument("--projects", default="razzo/projects.json")
    parser.add_argument("--objective", required=True)
    parser.add_argument("--live-head", required=True)
    parser.add_argument("--existing-prs")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    projects = load_projects(args.projects)
    objective_payload = json.loads(Path(args.objective).read_text(encoding="utf-8"))
    objective = objective_from_payload(objective_payload, projects=projects)

    existing: list[ExistingObjectivePR] = []
    if args.existing_prs:
        raw_existing = json.loads(Path(args.existing_prs).read_text(encoding="utf-8"))
        existing = [ExistingObjectivePR(**item) for item in raw_existing]

    decision = decide(objective, existing_prs=existing, live_integration_head=args.live_head)
    Path(args.output).write_text(
        json.dumps(decision.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if decision.action.startswith("BLOCKED_"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
