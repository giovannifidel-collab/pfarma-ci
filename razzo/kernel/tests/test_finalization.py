from __future__ import annotations

from dataclasses import replace

import pytest

from razzo.kernel.finalization import (
    FactoryFinalizationReport,
    FinalizationViolation,
    ProductDelivery,
    PRODUCT_REPOSITORIES,
    freeze_control_plane,
    substantial_product_candidate,
)


SHA = "a" * 40
MERGE_SHA = "b" * 40


def delivery(repository: str, pr: int, *, merged: bool = True, corrected: bool = False) -> ProductDelivery:
    return ProductDelivery(
        repository=repository,
        canonical_pr=pr,
        candidate_sha=SHA,
        integration_lane="integration/razzo" if "family-cloud" not in repository else "agent/bootstrap-family-cloud",
        merged=merged,
        merge_sha=MERGE_SHA if merged else None,
        product_ci_sha=SHA,
        product_ci_success=True,
        robot_qa_sha=SHA,
        robot_qa_success=True,
        user_journey_complete=True,
        error_recovery_verified=True,
        changed_product_files=4,
        corrected_after_failure=corrected,
    )


def report(deliveries: tuple[ProductDelivery, ...]) -> FactoryFinalizationReport:
    return FactoryFinalizationReport(
        deliveries=deliveries,
        duplicate_prs=0,
        collision_count=0,
        governance_only_prs=0,
        stale_leases_recovered=1,
        max_active_per_repository={repository: 1 for repository in PRODUCT_REPOSITORIES},
    )


def test_halfway_gate_requires_real_merge_and_autonomous_correction() -> None:
    report((delivery(PRODUCT_REPOSITORIES[0], 1001, corrected=True),)).validate_halfway()


@pytest.mark.parametrize(
    "mutation",
    [
        {"product_ci_success": False},
        {"robot_qa_success": False},
        {"robot_qa_sha": "c" * 40},
        {"user_journey_complete": False},
        {"error_recovery_verified": False},
        {"changed_product_files": 0},
        {"sensitive_surfaces": frozenset({"production-write"})},
    ],
)
def test_delivery_fails_closed_on_false_product_evidence(mutation: dict[str, object]) -> None:
    item = replace(delivery(PRODUCT_REPOSITORIES[0], 1001, corrected=True), **mutation)
    with pytest.raises(FinalizationViolation):
        report((item,)).validate_halfway()


def test_halfway_rejects_receipt_only_progress() -> None:
    with pytest.raises(FinalizationViolation, match="proven product delivery"):
        report(()).validate_halfway()


def test_halfway_rejects_uncorrected_happy_path_only() -> None:
    with pytest.raises(FinalizationViolation, match="corrected failed PR"):
        report((delivery(PRODUCT_REPOSITORIES[0], 1001),)).validate_halfway()


def test_final_gate_requires_all_product_repositories_and_two_merges() -> None:
    items = (
        delivery(PRODUCT_REPOSITORIES[0], 1001, corrected=True),
        delivery(PRODUCT_REPOSITORIES[1], 2001),
        delivery(PRODUCT_REPOSITORIES[2], 3001, merged=False),
    )
    report(items).validate_complete()


def test_final_gate_rejects_two_capabilities_in_one_repository() -> None:
    items = (
        delivery(PRODUCT_REPOSITORIES[0], 1001, corrected=True),
        delivery(PRODUCT_REPOSITORIES[0], 1002),
        delivery(PRODUCT_REPOSITORIES[2], 3001),
    )
    with pytest.raises(FinalizationViolation):
        report(items).validate_complete()


def test_substantial_candidate_requires_full_user_journey_and_product_files() -> None:
    candidate = {
        "reachable_from_ui": True,
        "business_logic": True,
        "error_recovery": True,
        "product_tests": True,
        "robot_journey": True,
        "integration_plan": True,
        "changed_paths": ["web/flow.ts", "lib/flow.ts", "tests/flow.test.ts"],
    }
    assert substantial_product_candidate(candidate)
    assert not substantial_product_candidate({**candidate, "robot_journey": False})
    assert not substantial_product_candidate({**candidate, "changed_paths": ["docs/plan.md", "razzo/state.json"]})


def test_control_plane_freezes_unless_product_is_blocked() -> None:
    assert freeze_control_plane("cosmetic dashboard improvement", blocking_product_issue=False)
    assert not freeze_control_plane("lease defect blocks all product delivery", blocking_product_issue=True)
    with pytest.raises(FinalizationViolation):
        freeze_control_plane("", blocking_product_issue=True)
