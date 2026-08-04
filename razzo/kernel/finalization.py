from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


PRODUCT_REPOSITORIES = (
    "giovannifidel-collab/project-giovanni",
    "giovannifidel-collab/pfarma-cloud",
    "giovannifidel-collab/family-cloud",
)

FORBIDDEN_SURFACES = frozenset(
    {
        "product-main",
        "production-write",
        "easyfarm-write",
        "real-order",
        "payment",
        "fiscal",
        "secret",
        "credential",
        "irreversible-migration",
        "irreplaceable-data",
    }
)


class FinalizationViolation(ValueError):
    pass


@dataclass(frozen=True)
class ProductDelivery:
    repository: str
    canonical_pr: int
    candidate_sha: str
    integration_lane: str
    merged: bool
    merge_sha: str | None
    product_ci_sha: str
    product_ci_success: bool
    robot_qa_sha: str
    robot_qa_success: bool
    user_journey_complete: bool
    error_recovery_verified: bool
    changed_product_files: int
    corrected_after_failure: bool = False
    sensitive_surfaces: frozenset[str] = frozenset()

    def validate(self) -> None:
        if self.repository not in PRODUCT_REPOSITORIES:
            raise FinalizationViolation(f"unexpected product repository: {self.repository}")
        if self.canonical_pr <= 0:
            raise FinalizationViolation("canonical PR must be positive")
        for label, sha in (
            ("candidate", self.candidate_sha),
            ("Product CI", self.product_ci_sha),
            ("Robot QA", self.robot_qa_sha),
        ):
            if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha):
                raise FinalizationViolation(f"{label} SHA must be a lowercase exact SHA")
        if not self.candidate_sha == self.product_ci_sha == self.robot_qa_sha:
            raise FinalizationViolation("candidate, Product CI and Robot QA must use one exact SHA")
        if not self.product_ci_success or not self.robot_qa_success:
            raise FinalizationViolation("both Product CI and independent Robot QA must be green")
        if not self.user_journey_complete:
            raise FinalizationViolation("delivery must complete a reachable end-to-end user journey")
        if not self.error_recovery_verified:
            raise FinalizationViolation("delivery must verify an error-recovery path")
        if self.changed_product_files < 1:
            raise FinalizationViolation("delivery must change real product files")
        forbidden = self.sensitive_surfaces & FORBIDDEN_SURFACES
        if forbidden:
            raise FinalizationViolation(f"forbidden sensitive surfaces: {sorted(forbidden)}")
        if self.merged:
            if self.merge_sha is None or len(self.merge_sha) != 40:
                raise FinalizationViolation("merged delivery requires an exact merge SHA")
        elif self.merge_sha is not None:
            raise FinalizationViolation("unmerged delivery cannot claim a merge SHA")


@dataclass(frozen=True)
class FactoryFinalizationReport:
    deliveries: tuple[ProductDelivery, ...]
    duplicate_prs: int
    collision_count: int
    governance_only_prs: int
    stale_leases_recovered: int
    max_active_per_repository: Mapping[str, int]

    def validate_halfway(self) -> None:
        """First-half gate: structural control plane and one proven product delivery."""
        self._validate_common()
        if len(self.deliveries) < 1:
            raise FinalizationViolation("50% gate requires at least one proven product delivery")
        if not any(delivery.merged for delivery in self.deliveries):
            raise FinalizationViolation("50% gate requires at least one integration-lane merge")
        if not any(delivery.corrected_after_failure for delivery in self.deliveries):
            raise FinalizationViolation("50% gate requires one autonomously corrected failed PR")

    def validate_complete(self) -> None:
        """Final gate: one substantial delivery per product repository."""
        self._validate_common()
        by_repository = {delivery.repository: delivery for delivery in self.deliveries}
        if set(by_repository) != set(PRODUCT_REPOSITORIES):
            raise FinalizationViolation("final proof requires exactly one delivery per product repository")
        if sum(delivery.merged for delivery in self.deliveries) < 2:
            raise FinalizationViolation("final proof requires at least two integration-lane merges")
        if not any(delivery.corrected_after_failure for delivery in self.deliveries):
            raise FinalizationViolation("final proof requires one autonomously corrected failed PR")

    def _validate_common(self) -> None:
        if self.duplicate_prs != 0:
            raise FinalizationViolation("duplicate PR count must be zero")
        if self.collision_count != 0:
            raise FinalizationViolation("collision count must be zero")
        if self.governance_only_prs != 0:
            raise FinalizationViolation("governance-only PRs are not product progress")
        for repository in PRODUCT_REPOSITORIES:
            if self.max_active_per_repository.get(repository) != 1:
                raise FinalizationViolation(f"repository slot invariant missing for {repository}")
        seen_repositories: set[str] = set()
        seen_prs: set[tuple[str, int]] = set()
        for delivery in self.deliveries:
            delivery.validate()
            if delivery.repository in seen_repositories:
                raise FinalizationViolation("more than one active delivery per repository")
            key = (delivery.repository, delivery.canonical_pr)
            if key in seen_prs:
                raise FinalizationViolation("duplicate canonical PR")
            seen_repositories.add(delivery.repository)
            seen_prs.add(key)


def substantial_product_candidate(candidate: Mapping[str, object]) -> bool:
    """Reject micro-work and governance churn before a capability is admitted."""
    required = {
        "reachable_from_ui",
        "business_logic",
        "error_recovery",
        "product_tests",
        "robot_journey",
        "integration_plan",
    }
    if any(candidate.get(key) is not True for key in required):
        return False
    changed_paths = candidate.get("changed_paths")
    if not isinstance(changed_paths, Sequence) or isinstance(changed_paths, (str, bytes)):
        return False
    product_paths = [str(path) for path in changed_paths if not str(path).startswith(("docs/", "razzo/", ".github/"))]
    return len(product_paths) >= 2


def freeze_control_plane(change_reason: str, blocking_product_issue: bool) -> bool:
    """After finalization, allow control-plane evolution only for a product-blocking defect."""
    if not change_reason.strip():
        raise FinalizationViolation("control-plane change requires a concrete reason")
    return not blocking_product_issue
