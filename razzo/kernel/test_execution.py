from __future__ import annotations

import unittest

from razzo.kernel.execution import (
    DeliveryObjective,
    ObservedPullRequest,
    resolve_canonical_pr,
    validate_exact_head,
    validate_receipt,
)


class ExecutionTests(unittest.TestCase):
    def objective(self) -> DeliveryObjective:
        return DeliveryObjective(
            project_id="pfarma-cloud",
            repository="giovannifidel-collab/pfarma-cloud",
            integration_lane="integration/razzo",
            title="Add a safe read-only inventory preview",
            acceptance=("real diff", "focused tests", "separate QA"),
            collision_domains=("inventory-preview",),
            max_workers=5,
        )

    def test_fingerprint_and_branch_are_stable(self) -> None:
        first = self.objective()
        second = self.objective()
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(first.branch, second.branch)
        self.assertTrue(first.branch.startswith("razzo/objective/pfarma-cloud-"))

    def test_worker_limit_is_hard_capped_at_five(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 1 and 5"):
            DeliveryObjective("p", "o/r", "integration/razzo", "t", ("a",), ("d",), 6)

    def test_resolver_updates_one_canonical_pr_and_blocks_duplicates(self) -> None:
        objective = self.objective()
        prs = [
            ObservedPullRequest(10, objective.branch, objective.pr_marker, "open", "a" * 40),
            ObservedPullRequest(12, objective.branch, objective.pr_marker, "open", "b" * 40),
        ]
        resolution = resolve_canonical_pr(objective, prs)
        self.assertEqual(resolution.action, "BLOCK_DUPLICATES")
        self.assertEqual(resolution.canonical_pr, 12)
        self.assertEqual(resolution.duplicate_prs, (10,))

    def test_exact_head_fails_closed(self) -> None:
        validate_exact_head("a" * 40, "a" * 40)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            validate_exact_head("a" * 40, "b" * 40)

    def test_receipt_requires_diff_ci_and_separate_robot_qa(self) -> None:
        objective = self.objective()
        receipt = {
            "objective_fingerprint": objective.fingerprint,
            "candidate_sha": "c" * 40,
            "expected_head": "a" * 40,
            "tests": "passed",
            "product_ci": "passed",
            "robot_qa": "passed",
            "changed_files": ["src/preview.ts"],
            "worker_count": 3,
        }
        validate_receipt(receipt, objective, "a" * 40)
        receipt["robot_qa"] = "missing"
        with self.assertRaisesRegex(ValueError, "Robot QA"):
            validate_receipt(receipt, objective, "a" * 40)


if __name__ == "__main__":
    unittest.main()
