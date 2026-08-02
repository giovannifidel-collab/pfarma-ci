from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from .capability import CapabilityPlan, CapabilityWave, normalize_surface

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class ProjectContract:
    project_id: str
    repository: str
    integration_lane: str
    max_builders: int = 5

    def validate(self) -> None:
        if not self.project_id or not self.repository or not self.integration_lane:
            raise ValueError("project contract requires id, repository and integration lane")
        if not 1 <= self.max_builders <= 5:
            raise ValueError("project contract max_builders must be between 1 and 5")


@dataclass(frozen=True)
class CanonicalShred:
    shred_id: str
    capability_node_id: str
    responsibility: str
    dependencies: tuple[str, ...]
    allowed_surfaces: tuple[str, ...]
    acceptance_subset: tuple[str, ...]
    collision_domain: str
    verification: tuple[str, ...]
    homo_level: str

    def validate(self) -> None:
        if not re.fullmatch(r"S[0-9]{2,3}", self.shred_id):
            raise ValueError("canonical shred id must match SNN or SNNN")
        if not re.fullmatch(r"N[0-9]{3,4}", self.capability_node_id):
            raise ValueError("canonical shred requires a capability node id")
        if not self.responsibility.strip():
            raise ValueError("canonical shred requires responsibility")
        if self.shred_id in self.dependencies:
            raise ValueError("canonical shred cannot depend on itself")
        if not self.allowed_surfaces:
            raise ValueError("canonical shred requires allowed surfaces")
        for surface in self.allowed_surfaces:
            normalize_surface(surface)
        if not self.acceptance_subset or not self.collision_domain or not self.verification:
            raise ValueError("canonical shred requires acceptance, collision and verification")


@dataclass(frozen=True)
class CanonicalObjective:
    capability_id: str
    revision_id: str
    wave_id: str
    project: ProjectContract
    base_sha: str
    title: str
    user_outcome: str
    acceptance: tuple[str, ...]
    collision_domains: tuple[str, ...]
    shreds: tuple[CanonicalShred, ...]

    def validate(self) -> None:
        self.project.validate()
        for value, label in (
            (self.capability_id, "capability_id"),
            (self.revision_id, "revision_id"),
            (self.wave_id, "wave_id"),
        ):
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError(f"{label} must be a lowercase SHA-256")
        if not _SHA_RE.fullmatch(self.base_sha):
            raise ValueError("canonical objective base_sha must be exact")
        if not self.title.strip() or not self.user_outcome.strip():
            raise ValueError("canonical objective requires title and user outcome")
        if len(self.acceptance) < 2:
            raise ValueError("canonical objective requires at least two acceptance criteria")
        if not self.shreds or len(self.shreds) > self.project.max_builders:
            raise ValueError("canonical objective shred count is outside project limits")
        ids = [shred.shred_id for shred in self.shreds]
        if len(ids) != len(set(ids)):
            raise ValueError("canonical objective has duplicate shred ids")
        node_ids = [shred.capability_node_id for shred in self.shreds]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("canonical objective has duplicate capability node ids")
        known = set(ids)
        for shred in self.shreds:
            shred.validate()
            unknown = set(shred.dependencies) - known
            if unknown:
                raise ValueError(f"unknown canonical shred dependencies: {sorted(unknown)}")
        if set(self.collision_domains) != {shred.collision_domain for shred in self.shreds}:
            raise ValueError("canonical objective collision domains do not match shreds")

    @property
    def fingerprint(self) -> str:
        self.validate()
        return _digest(
            {
                "capability_id": self.capability_id,
                "revision_id": self.revision_id,
                "wave_id": self.wave_id,
                "project_id": self.project.project_id,
                "repository": self.project.repository,
                "integration_lane": self.project.integration_lane,
                "base_sha": self.base_sha,
                "acceptance": sorted(self.acceptance),
                "shreds": [
                    {
                        "shred_id": shred.shred_id,
                        "node_id": shred.capability_node_id,
                        "dependencies": list(shred.dependencies),
                        "collision_domain": shred.collision_domain,
                        "verification": list(shred.verification),
                    }
                    for shred in self.shreds
                ],
            }
        )

    @property
    def branch(self) -> str:
        return f"razzo/o/{self.fingerprint[:20]}"

    @property
    def pr_marker(self) -> str:
        return f"<!-- razzo-objective:{self.fingerprint} -->"

    def to_controller_payload(self) -> dict[str, Any]:
        self.validate()
        return {
            "project_id": self.project.project_id,
            "base_sha": self.base_sha,
            "goal": f"{self.title} [wave:{self.wave_id[:16]}]",
            "user_outcome": self.user_outcome,
            "acceptance_criteria": list(self.acceptance),
            "collision_domains": list(self.collision_domains),
            "shreds": [
                {
                    "shred_id": shred.shred_id,
                    "responsibility": shred.responsibility,
                    "dependencies": list(shred.dependencies),
                    "allowed_surfaces": list(shred.allowed_surfaces),
                    "acceptance_subset": list(shred.acceptance_subset),
                    "collision_domain": shred.collision_domain,
                    "verification": list(shred.verification),
                    "capability_node_id": shred.capability_node_id,
                    "homo_level": shred.homo_level,
                }
                for shred in self.shreds
            ],
            "metadata": {
                "capability_id": self.capability_id,
                "revision_id": self.revision_id,
                "wave_id": self.wave_id,
                "canonical_fingerprint": self.fingerprint,
                "verification_by_shred": {
                    shred.shred_id: list(shred.verification) for shred in self.shreds
                },
            },
        }

    def to_model_objective(self) -> Any:
        """Compatibility edge for the existing controller model."""

        from .model import DeliveryObjective, ObjectiveState, ShredContract

        objective = DeliveryObjective(
            project_id=self.project.project_id,
            repository=self.project.repository,
            integration_lane=self.project.integration_lane,
            base_sha=self.base_sha,
            goal=f"{self.title} [wave:{self.wave_id[:16]}]",
            user_outcome=self.user_outcome,
            acceptance_criteria=self.acceptance,
            collision_domains=self.collision_domains,
            state=ObjectiveState.DISCOVERED,
            shreds=tuple(
                ShredContract(
                    shred_id=shred.shred_id,
                    responsibility=shred.responsibility,
                    dependencies=shred.dependencies,
                    allowed_surfaces=shred.allowed_surfaces,
                    acceptance_subset=shred.acceptance_subset,
                    collision_domain=shred.collision_domain,
                )
                for shred in self.shreds
            ),
        )
        objective.validate()
        return objective

    def to_execution_objective(self) -> Any:
        """Compatibility edge for the existing execution/Organism model."""

        from .execution import DeliveryObjective

        return DeliveryObjective(
            project_id=self.project.project_id,
            repository=self.project.repository,
            integration_lane=self.project.integration_lane,
            title=f"{self.title} [wave:{self.wave_id[:16]}]",
            acceptance=self.acceptance,
            collision_domains=self.collision_domains,
            max_workers=min(self.project.max_builders, len(self.shreds)),
        )


@dataclass(frozen=True)
class ExactHeadEvidence:
    candidate_sha: str
    product_ci_sha: str
    robot_qa_sha: str
    expected_head_sha: str
    changed_files: tuple[str, ...]
    assertions: tuple[str, ...]

    def validate(self) -> None:
        shas = (
            self.candidate_sha,
            self.product_ci_sha,
            self.robot_qa_sha,
            self.expected_head_sha,
        )
        if any(not _SHA_RE.fullmatch(value) for value in shas):
            raise ValueError("all evidence SHAs must be exact lowercase commit SHAs")
        if len(set(shas)) != 1:
            raise ValueError("candidate, CI, QA and expected head must be the same SHA")
        if not self.changed_files:
            raise ValueError("exact-head evidence requires a real diff")
        for path in self.changed_files:
            normalize_surface(path)
        if not self.assertions:
            raise ValueError("exact-head evidence requires functional assertions")


def build_canonical_objective(
    plan: CapabilityPlan,
    wave: CapabilityWave,
    project: ProjectContract,
) -> CanonicalObjective:
    payload = plan.to_controller_payload(wave)
    project.validate()
    if project.project_id != plan.spec.project_id:
        raise ValueError("project contract does not match capability project")
    if len(payload["shreds"]) > project.max_builders:
        raise ValueError("wave exceeds project builder limit")

    shreds = tuple(
        CanonicalShred(
            shred_id=str(raw["shred_id"]),
            capability_node_id=str(raw["capability_node_id"]),
            responsibility=str(raw["responsibility"]),
            dependencies=tuple(str(x) for x in raw["dependencies"]),
            allowed_surfaces=tuple(str(x) for x in raw["allowed_surfaces"]),
            acceptance_subset=tuple(str(x) for x in raw["acceptance_subset"]),
            collision_domain=str(raw["collision_domain"]),
            verification=tuple(str(x) for x in raw["verification"]),
            homo_level=str(raw["homo_level"]),
        )
        for raw in payload["shreds"]
    )
    objective = CanonicalObjective(
        capability_id=plan.capability_id,
        revision_id=plan.revision_id,
        wave_id=wave.wave_id,
        project=project,
        base_sha=wave.exact_base_sha,
        title=plan.spec.title,
        user_outcome=plan.spec.user_outcome,
        acceptance=tuple(str(x) for x in payload["acceptance_criteria"]),
        collision_domains=tuple(shred.collision_domain for shred in shreds),
        shreds=shreds,
    )
    objective.validate()
    return objective


def assert_verification_preserved(
    objective: CanonicalObjective,
    expected_commands: Iterable[str],
) -> None:
    actual = {command for shred in objective.shreds for command in shred.verification}
    expected = set(expected_commands)
    missing = expected - actual
    if missing:
        raise ValueError(f"verification commands were lost by the bridge: {sorted(missing)}")
