from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class ObjectiveState(str, Enum):
    DISCOVERED = "DISCOVERED"
    PLANNED = "PLANNED"
    BUILDING = "BUILDING"
    ASSEMBLING = "ASSEMBLING"
    CANDIDATE_READY = "CANDIDATE_READY"
    VERIFYING = "VERIFYING"
    NEEDS_REPLAN = "NEEDS_REPLAN"
    MERGE_READY = "MERGE_READY"
    MERGED = "MERGED"
    FAILED = "FAILED"


_ALLOWED_TRANSITIONS: dict[ObjectiveState, set[ObjectiveState]] = {
    ObjectiveState.DISCOVERED: {ObjectiveState.PLANNED, ObjectiveState.FAILED},
    ObjectiveState.PLANNED: {ObjectiveState.BUILDING, ObjectiveState.NEEDS_REPLAN, ObjectiveState.FAILED},
    ObjectiveState.BUILDING: {ObjectiveState.ASSEMBLING, ObjectiveState.NEEDS_REPLAN, ObjectiveState.FAILED},
    ObjectiveState.ASSEMBLING: {ObjectiveState.CANDIDATE_READY, ObjectiveState.NEEDS_REPLAN, ObjectiveState.FAILED},
    ObjectiveState.CANDIDATE_READY: {ObjectiveState.VERIFYING, ObjectiveState.NEEDS_REPLAN, ObjectiveState.FAILED},
    ObjectiveState.VERIFYING: {ObjectiveState.MERGE_READY, ObjectiveState.NEEDS_REPLAN, ObjectiveState.FAILED},
    ObjectiveState.NEEDS_REPLAN: {ObjectiveState.PLANNED, ObjectiveState.FAILED},
    ObjectiveState.MERGE_READY: {ObjectiveState.MERGED, ObjectiveState.NEEDS_REPLAN, ObjectiveState.FAILED},
    ObjectiveState.MERGED: set(),
    ObjectiveState.FAILED: set(),
}


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()


def objective_fingerprint(
    *,
    project_id: str,
    goal: str,
    user_outcome: str,
    acceptance_criteria: Iterable[str],
    collision_domains: Iterable[str],
) -> str:
    payload = {
        "project_id": project_id.strip(),
        "goal": _clean_text(goal),
        "user_outcome": _clean_text(user_outcome),
        "acceptance_criteria": sorted(_clean_text(item) for item in acceptance_criteria),
        "collision_domains": sorted(item.strip().strip("/") for item in collision_domains),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def objective_branch(fingerprint: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise ValueError("objective fingerprint must be a 64-character lowercase hex digest")
    return f"razzo/o/{fingerprint[:20]}"


def shred_branch(fingerprint: str, shred_id: str) -> str:
    if not re.fullmatch(r"S[0-9]{2,3}", shred_id):
        raise ValueError("shred_id must match SNN or SNNN")
    return f"{objective_branch(fingerprint)}/s/{shred_id}"


@dataclass(frozen=True)
class ShredContract:
    shred_id: str
    responsibility: str
    dependencies: tuple[str, ...] = ()
    allowed_surfaces: tuple[str, ...] = ()
    acceptance_subset: tuple[str, ...] = ()
    collision_domain: str = ""

    def validate(self) -> None:
        if not re.fullmatch(r"S[0-9]{2,3}", self.shred_id):
            raise ValueError(f"invalid shred id: {self.shred_id}")
        if not self.responsibility.strip():
            raise ValueError(f"missing responsibility for {self.shred_id}")
        if self.shred_id in self.dependencies:
            raise ValueError(f"self dependency for {self.shred_id}")
        if not self.allowed_surfaces:
            raise ValueError(f"no allowed surfaces for {self.shred_id}")
        if not self.acceptance_subset:
            raise ValueError(f"no acceptance subset for {self.shred_id}")
        if not self.collision_domain.strip():
            raise ValueError(f"missing collision domain for {self.shred_id}")


@dataclass
class DeliveryObjective:
    project_id: str
    repository: str
    integration_lane: str
    base_sha: str
    goal: str
    user_outcome: str
    acceptance_criteria: tuple[str, ...]
    collision_domains: tuple[str, ...]
    state: ObjectiveState = ObjectiveState.DISCOVERED
    shreds: tuple[ShredContract, ...] = field(default_factory=tuple)
    candidate_sha: str | None = None
    pr_number: int | None = None

    @property
    def fingerprint(self) -> str:
        return objective_fingerprint(
            project_id=self.project_id,
            goal=self.goal,
            user_outcome=self.user_outcome,
            acceptance_criteria=self.acceptance_criteria,
            collision_domains=self.collision_domains,
        )

    @property
    def branch(self) -> str:
        return objective_branch(self.fingerprint)

    def validate(self) -> None:
        if not self.project_id.strip() or not self.repository.strip():
            raise ValueError("project_id and repository are required")
        if not self.integration_lane.strip():
            raise ValueError("integration_lane is required")
        if not re.fullmatch(r"[0-9a-f]{40}", self.base_sha):
            raise ValueError("base_sha must be an exact 40-character commit SHA")
        if not self.goal.strip() or not self.user_outcome.strip():
            raise ValueError("goal and user_outcome are required")
        if len(self.acceptance_criteria) < 2:
            raise ValueError("at least two acceptance criteria are required")
        if not self.collision_domains:
            raise ValueError("at least one collision domain is required")

        ids = [shred.shred_id for shred in self.shreds]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate shred id")
        domains = [shred.collision_domain for shred in self.shreds]
        if len(domains) != len(set(domains)):
            raise ValueError("duplicate shred collision domain")
        known = set(ids)
        for shred in self.shreds:
            shred.validate()
            unknown = set(shred.dependencies) - known
            if unknown:
                raise ValueError(f"unknown dependencies for {shred.shred_id}: {sorted(unknown)}")

    def transition(self, target: ObjectiveState) -> None:
        if target not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"invalid objective transition: {self.state.value} -> {target.value}")
        self.state = target

    def bind_candidate(self, *, candidate_sha: str, pr_number: int) -> None:
        if self.state not in {ObjectiveState.ASSEMBLING, ObjectiveState.CANDIDATE_READY}:
            raise ValueError("candidate can be bound only during assembly")
        if not re.fullmatch(r"[0-9a-f]{40}", candidate_sha):
            raise ValueError("candidate_sha must be an exact 40-character commit SHA")
        if pr_number < 1:
            raise ValueError("pr_number must be positive")
        self.candidate_sha = candidate_sha
        self.pr_number = pr_number
        self.state = ObjectiveState.CANDIDATE_READY

    def exact_head_verified(self, *, product_ci_sha: str, qa_sha: str) -> bool:
        return bool(
            self.candidate_sha
            and product_ci_sha == self.candidate_sha
            and qa_sha == self.candidate_sha
        )
