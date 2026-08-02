from __future__ import annotations

import unittest

from razzo.kernel.model import (
    DeliveryObjective,
    ObjectiveState,
    ShredContract,
    objective_branch,
    objective_fingerprint,
    shred_branch,
)


BASE_SHA = "a" * 40
CANDIDATE_SHA = "b" * 40


def sample_objective() -> DeliveryObjective:
    return DeliveryObjective(
        project_id="pfarma-cloud",
        repository="giovannifidel-collab/pfarma-cloud",
        integration_lane="integration/razzo",
        base_sha=BASE_SHA,
        goal="Add a real read-only inventory transfer preview",
        user_outcome="An operator can inspect balances before any write",
        acceptance_criteria=(
            "Valid transfers show source and destination balances",
            "Invalid transfers fail without production writes",
        ),
        collision_domains=("inventory/interwarehouse-transfer",),
        shreds=(
            ShredContract(
                shred_id="S01",
                responsibility="Implement the bounded domain contract",
                allowed_surfaces=("api/interwarehouse_transfer_preview.py",),
                acceptance_subset=("Valid transfers show source and destination balances",),
                collision_domain="inventory/interwarehouse-transfer/domain",
            ),
            ShredContract(
                shred_id="S02",
                responsibility="Add independent focused acceptance tests",
                dependencies=("S01",),
                allowed_surfaces=("tests/test_interwarehouse_transfer_preview.py",),
                acceptance_subset=("Invalid transfers fail without production writes",),
                collision_domain="inventory/interwarehouse-transfer/tests",
            ),
        ),
    )


class ObjectiveKernelTests(unittest.TestCase):
    def test_fingerprint_is_deterministic_and_run_independent(self) -> None:
        first = objective_fingerprint(
            project_id="pfarma-cloud",
            goal="  Add preview ",
            user_outcome="Operator sees balances",
            acceptance_criteria=("B", "A"),
            collision_domains=("inventory/b", "inventory/a"),
        )
        second = objective_fingerprint(
            project_id="pfarma-cloud",
            goal="add preview",
            user_outcome="operator sees balances",
            acceptance_criteria=("A", "B"),
            collision_domains=("inventory/a", "inventory/b"),
        )
        self.assertEqual(first, second)
        self.assertEqual(objective_branch(first), f"razzo/o/{first[:20]}")
        self.assertEqual(shred_branch(first, "S01"), f"razzo/o/{first[:20]}/s/S01")

    def test_objective_validates_dag_and_transitions(self) -> None:
        objective = sample_objective()
        objective.validate()
        objective.transition(ObjectiveState.PLANNED)
        objective.transition(ObjectiveState.BUILDING)
        objective.transition(ObjectiveState.ASSEMBLING)
        objective.bind_candidate(candidate_sha=CANDIDATE_SHA, pr_number=2045)
        objective.transition(ObjectiveState.VERIFYING)
        self.assertTrue(
            objective.exact_head_verified(
                product_ci_sha=CANDIDATE_SHA,
                qa_sha=CANDIDATE_SHA,
            )
        )
        objective.transition(ObjectiveState.MERGE_READY)
        objective.transition(ObjectiveState.MERGED)

    def test_wrong_sha_cannot_satisfy_exact_head_gate(self) -> None:
        objective = sample_objective()
        objective.state = ObjectiveState.ASSEMBLING
        objective.bind_candidate(candidate_sha=CANDIDATE_SHA, pr_number=2045)
        self.assertFalse(
            objective.exact_head_verified(
                product_ci_sha=CANDIDATE_SHA,
                qa_sha="c" * 40,
            )
        )

    def test_invalid_transition_fails_closed(self) -> None:
        objective = sample_objective()
        with self.assertRaises(ValueError):
            objective.transition(ObjectiveState.MERGED)


if __name__ == "__main__":
    unittest.main()
