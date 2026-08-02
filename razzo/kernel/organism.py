from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .execution import DeliveryObjective

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class FictionalRole(str, Enum):
    CARTOGRAPHER = "CARTOGRAPHER"
    SPECIFIER = "SPECIFIER"
    MAKER_MINIMAL = "MAKER_MINIMAL"
    MAKER_ROBUST = "MAKER_ROBUST"
    BREAKER = "BREAKER"


_SPECULATIVE_ROLES = {
    FictionalRole.MAKER_MINIMAL,
    FictionalRole.MAKER_ROBUST,
}


@dataclass(frozen=True)
class RoleContract:
    role: FictionalRole
    phase: int
    purpose: str
    required_inputs: tuple[str, ...]
    required_outputs: tuple[str, ...]
    speculative: bool = False

    def validate(self) -> None:
        if self.phase < 0:
            raise ValueError("role phase cannot be negative")
        if not self.purpose.strip():
            raise ValueError(f"{self.role.value} requires a purpose")
        if not self.required_inputs or not self.required_outputs:
            raise ValueError(f"{self.role.value} requires explicit inputs and outputs")
        if self.speculative != (self.role in _SPECULATIVE_ROLES):
            raise ValueError(f"{self.role.value} speculative flag is inconsistent")


@dataclass(frozen=True)
class CellPlan:
    objective_fingerprint: str
    project_id: str
    repository: str
    base_sha: str
    canonical_branch: str
    canonical_pr_marker: str
    acceptance: tuple[str, ...]
    collision_domains: tuple[str, ...]
    roles: tuple[RoleContract, ...]
    max_parallel: int = 2

    def validate(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.objective_fingerprint):
            raise ValueError("objective fingerprint must be a lowercase SHA-256")
        if not _SHA_RE.fullmatch(self.base_sha):
            raise ValueError("base_sha must be an exact lowercase 40-character SHA")
        if not self.project_id or not self.repository:
            raise ValueError("cell requires project_id and repository")
        if not self.canonical_branch.startswith("razzo/objective/"):
            raise ValueError("cell must use the canonical objective branch")
        if self.objective_fingerprint not in self.canonical_pr_marker:
            raise ValueError("cell PR marker must contain the objective fingerprint")
        if not self.acceptance or not self.collision_domains:
            raise ValueError("cell requires acceptance criteria and collision domains")
        if not 1 <= self.max_parallel <= 5:
            raise ValueError("max_parallel must be between 1 and 5")

        if len(self.roles) != len(FictionalRole):
            raise ValueError("cell must contain exactly one contract for every fictional role")
        observed = {contract.role for contract in self.roles}
        if observed != set(FictionalRole):
            raise ValueError("cell role set is incomplete or duplicated")
        for contract in self.roles:
            contract.validate()

        phases: dict[int, list[RoleContract]] = {}
        for contract in self.roles:
            phases.setdefault(contract.phase, []).append(contract)
        if max(len(items) for items in phases.values()) > self.max_parallel:
            raise ValueError("role graph exceeds max_parallel")
        if len(phases.get(0, [])) != 2 or len(phases.get(1, [])) != 2 or len(phases.get(2, [])) != 1:
            raise ValueError("cell must use the 2 -> 2 -> 1 role graph")


def compile_cell(objective: DeliveryObjective, *, base_sha: str) -> CellPlan:
    if not _SHA_RE.fullmatch(base_sha):
        raise ValueError("base_sha must be an exact lowercase 40-character SHA")

    roles = (
        RoleContract(
            role=FictionalRole.CARTOGRAPHER,
            phase=0,
            purpose="Map only the repository surfaces needed by the objective and record forbidden surfaces.",
            required_inputs=("objective", "exact_base_sha", "repository_manifest"),
            required_outputs=("context_map", "allowed_surfaces", "forbidden_surfaces"),
        ),
        RoleContract(
            role=FictionalRole.SPECIFIER,
            phase=0,
            purpose="Translate the user outcome into executable invariants and product acceptance tests.",
            required_inputs=("objective", "exact_base_sha", "product_contract"),
            required_outputs=("invariants", "acceptance_tests", "failure_oracles"),
        ),
        RoleContract(
            role=FictionalRole.MAKER_MINIMAL,
            phase=1,
            purpose="Produce the smallest complete candidate satisfying every invariant.",
            required_inputs=("context_map", "invariants", "acceptance_tests"),
            required_outputs=("candidate_ref", "candidate_sha", "changed_files", "test_evidence"),
            speculative=True,
        ),
        RoleContract(
            role=FictionalRole.MAKER_ROBUST,
            phase=1,
            purpose="Produce an independent resilience-first candidate for the same objective.",
            required_inputs=("context_map", "invariants", "failure_oracles"),
            required_outputs=("candidate_ref", "candidate_sha", "changed_files", "test_evidence"),
            speculative=True,
        ),
        RoleContract(
            role=FictionalRole.BREAKER,
            phase=2,
            purpose="Attack both candidates, verify exact-head evidence, and reject unsupported claims.",
            required_inputs=("candidate_evidence", "acceptance_tests", "failure_oracles"),
            required_outputs=("adversarial_findings", "eligible_candidates", "robot_qa_plan"),
        ),
    )

    plan = CellPlan(
        objective_fingerprint=objective.fingerprint,
        project_id=objective.project_id,
        repository=objective.repository,
        base_sha=base_sha,
        canonical_branch=objective.branch,
        canonical_pr_marker=objective.pr_marker,
        acceptance=objective.acceptance,
        collision_domains=objective.collision_domains,
        roles=roles,
        max_parallel=min(2, objective.max_workers),
    )
    plan.validate()
    return plan


@dataclass(frozen=True)
class CandidateEvidence:
    role: FictionalRole
    base_sha: str
    candidate_sha: str
    candidate_ref: str
    changed_files: tuple[str, ...]
    acceptance_covered: tuple[str, ...]
    tests_passed: bool
    product_ci_passed: bool
    risk_flags: tuple[str, ...] = ()

    def validate(self, plan: CellPlan) -> None:
        if self.role not in _SPECULATIVE_ROLES:
            raise ValueError("only maker roles may submit candidates")
        if self.base_sha != plan.base_sha:
            raise ValueError("candidate was not built from the cell exact base SHA")
        if not _SHA_RE.fullmatch(self.candidate_sha):
            raise ValueError("candidate_sha must be an exact lowercase 40-character SHA")
        if not self.candidate_ref.strip():
            raise ValueError("candidate_ref is required")
        if not self.changed_files:
            raise ValueError("candidate requires a real diff")
        if len(self.changed_files) != len(set(self.changed_files)):
            raise ValueError("candidate changed_files must be unique")
        missing = set(plan.acceptance) - set(self.acceptance_covered)
        if missing:
            raise ValueError(f"candidate does not cover acceptance criteria: {sorted(missing)}")
        if not self.tests_passed or not self.product_ci_passed:
            raise ValueError("candidate must pass focused tests and Product CI")


@dataclass(frozen=True)
class TournamentResult:
    winner: CandidateEvidence
    rejected: tuple[CandidateEvidence, ...]
    reason: str


def select_candidate(plan: CellPlan, candidates: Iterable[CandidateEvidence]) -> TournamentResult:
    plan.validate()
    items = tuple(candidates)
    if not items:
        raise ValueError("candidate tournament requires at least one candidate")

    seen_roles: set[FictionalRole] = set()
    seen_shas: set[str] = set()
    for candidate in items:
        candidate.validate(plan)
        if candidate.role in seen_roles:
            raise ValueError(f"duplicate candidate role: {candidate.role.value}")
        if candidate.candidate_sha in seen_shas:
            raise ValueError("candidate SHA must be unique")
        seen_roles.add(candidate.role)
        seen_shas.add(candidate.candidate_sha)

    def score(candidate: CandidateEvidence) -> tuple[int, int, int, str]:
        role_bias = 0 if candidate.role is FictionalRole.MAKER_MINIMAL else 1
        return (
            len(candidate.risk_flags),
            len(candidate.changed_files),
            role_bias,
            candidate.candidate_sha,
        )

    ordered = sorted(items, key=score)
    winner = ordered[0]
    return TournamentResult(
        winner=winner,
        rejected=tuple(ordered[1:]),
        reason=(
            "selected by deterministic evidence tournament: fewest risk flags, "
            "smallest complete diff, then stable role/SHA tie-break"
        ),
    )


@dataclass(frozen=True)
class FinalEvidence:
    candidate_sha: str
    expected_head: str
    product_ci_sha: str
    robot_qa_sha: str
    changed_files: tuple[str, ...]
    functional_assertions: tuple[str, ...]


def verify_final_evidence(plan: CellPlan, evidence: FinalEvidence) -> None:
    plan.validate()
    shas = (
        evidence.candidate_sha,
        evidence.expected_head,
        evidence.product_ci_sha,
        evidence.robot_qa_sha,
    )
    if any(not _SHA_RE.fullmatch(value) for value in shas):
        raise ValueError("final evidence requires exact lowercase 40-character SHAs")
    if len(set(shas)) != 1:
        raise ValueError("candidate, expected head, Product CI and Robot QA must verify the same SHA")
    if not evidence.changed_files:
        raise ValueError("final evidence requires a real diff")
    if not evidence.functional_assertions:
        raise ValueError("final evidence requires functional Robot QA assertions")
