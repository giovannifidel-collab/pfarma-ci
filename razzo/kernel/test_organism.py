from __future__ import annotations

import unittest

from razzo.kernel.execution import DeliveryObjective
from razzo.kernel.organism import (
    CandidateEvidence,
    FictionalRole,
    FinalEvidence,
    compile_cell,
    select_candidate,
    verify_final_evidence,
)


class OrganismCompilerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.objective = DeliveryObjective(
            project_id="project-giovanni",
            repository="giovannifidel-collab/project-giovanni",
            integration_lane="integration/razzo",
            title="Complete the guided onboarding outcome",
            acceptance=(
                "user can complete the guided flow",
                "failure state is recoverable",
            ),
            collision_domains=("app/onboarding", "tests/onboarding"),
            max_workers=5,
        )
        self.base_sha = "a" * 40
        self.plan = compile_cell(self.objective, base_sha=self.base_sha)

    def test_compile_cell_uses_five_fictional_roles_and_real_parallel_layers(self) -> None:
        self.assertEqual(5, len(self.plan.roles))
        self.assertEqual(2, self.plan.max_parallel)
        phases = [role.phase for role in self.plan.roles]
        self.assertEqual([0, 0, 1, 1, 2], phases)
        self.assertEqual(self.objective.branch, self.plan.canonical_branch)
        self.assertEqual(self.objective.pr_marker, self.plan.canonical_pr_marker)

    def test_tournament_selects_lower_risk_complete_candidate(self) -> None:
        minimal = CandidateEvidence(
            role=FictionalRole.MAKER_MINIMAL,
            base_sha=self.base_sha,
            candidate_sha="b" * 40,
            candidate_ref="refs/razzo-candidates/minimal",
            changed_files=("app/onboarding/page.tsx",),
            acceptance_covered=self.objective.acceptance,
            tests_passed=True,
            product_ci_passed=True,
            risk_flags=("missing-browser-fallback",),
        )
        robust = CandidateEvidence(
            role=FictionalRole.MAKER_ROBUST,
            base_sha=self.base_sha,
            candidate_sha="c" * 40,
            candidate_ref="refs/razzo-candidates/robust",
            changed_files=(
                "app/onboarding/page.tsx",
                "tests/onboarding/recovery.test.ts",
            ),
            acceptance_covered=self.objective.acceptance,
            tests_passed=True,
            product_ci_passed=True,
        )

        result = select_candidate(self.plan, (minimal, robust))

        self.assertEqual(FictionalRole.MAKER_ROBUST, result.winner.role)
        self.assertEqual((minimal,), result.rejected)

    def test_candidate_with_incomplete_acceptance_is_rejected(self) -> None:
        incomplete = CandidateEvidence(
            role=FictionalRole.MAKER_MINIMAL,
            base_sha=self.base_sha,
            candidate_sha="b" * 40,
            candidate_ref="refs/razzo-candidates/minimal",
            changed_files=("app/onboarding/page.tsx",),
            acceptance_covered=(self.objective.acceptance[0],),
            tests_passed=True,
            product_ci_passed=True,
        )

        with self.assertRaisesRegex(ValueError, "does not cover acceptance criteria"):
            select_candidate(self.plan, (incomplete,))

    def test_final_gate_requires_same_exact_head_for_product_ci_and_robot_qa(self) -> None:
        evidence = FinalEvidence(
            candidate_sha="d" * 40,
            expected_head="d" * 40,
            product_ci_sha="d" * 40,
            robot_qa_sha="e" * 40,
            changed_files=("app/onboarding/page.tsx",),
            functional_assertions=("guided flow completes in browser",),
        )

        with self.assertRaisesRegex(ValueError, "must verify the same SHA"):
            verify_final_evidence(self.plan, evidence)

    def test_final_gate_accepts_real_diff_and_functional_exact_head_evidence(self) -> None:
        evidence = FinalEvidence(
            candidate_sha="d" * 40,
            expected_head="d" * 40,
            product_ci_sha="d" * 40,
            robot_qa_sha="d" * 40,
            changed_files=("app/onboarding/page.tsx",),
            functional_assertions=("guided flow completes in browser",),
        )

        verify_final_evidence(self.plan, evidence)


if __name__ == "__main__":
    unittest.main()
