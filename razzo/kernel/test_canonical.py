from __future__ import annotations

import unittest
from dataclasses import replace

from .canonical import ExactHeadEvidence, ProjectContract, assert_verification_preserved, build_canonical_objective
from .testing import make_plan


class CanonicalBridgeTests(unittest.TestCase):
    def setUp(self):
        self.plan = make_plan()
        self.wave = self.plan.next_wave()
        self.project = ProjectContract(
            project_id="pfarma-cloud",
            repository="giovannifidel-collab/pfarma-cloud",
            integration_lane="integration/razzo",
            max_builders=5,
        )
        self.objective = build_canonical_objective(self.plan, self.wave, self.project)

    def test_canonical_objective_is_deterministic(self):
        other = build_canonical_objective(self.plan, self.wave, self.project)
        self.assertEqual(self.objective.fingerprint, other.fingerprint)

    def test_branch_excludes_run_id(self):
        self.assertTrue(self.objective.branch.startswith("razzo/o/"))
        self.assertNotIn("run", self.objective.branch)

    def test_controller_payload_preserves_all_shreds(self):
        payload = self.objective.to_controller_payload()
        self.assertEqual(len(payload["shreds"]), len(self.wave.node_ids))

    def test_controller_payload_preserves_verification(self):
        payload = self.objective.to_controller_payload()
        self.assertEqual(
            set(payload["metadata"]["verification_by_shred"]),
            {shred.shred_id for shred in self.objective.shreds},
        )

    def test_model_adapter_validates(self):
        model = self.objective.to_model_objective()
        model.validate()
        self.assertEqual(len(model.shreds), len(self.objective.shreds))

    def test_execution_adapter_validates(self):
        execution = self.objective.to_execution_objective()
        self.assertEqual(execution.max_workers, 5)
        self.assertEqual(execution.collision_domains, self.objective.collision_domains)

    def test_project_mismatch_is_rejected(self):
        bad = replace(self.project, project_id="other")
        with self.assertRaisesRegex(ValueError, "does not match"):
            build_canonical_objective(self.plan, self.wave, bad)

    def test_verification_loss_is_detected(self):
        with self.assertRaisesRegex(ValueError, "lost"):
            assert_verification_preserved(self.objective, ("missing command",))


class ExactHeadEvidenceTests(unittest.TestCase):
    def test_accepts_matching_evidence(self):
        sha = "b" * 40
        ExactHeadEvidence(sha, sha, sha, sha, ("src/a.py",), ("journey passed",)).validate()

    def test_rejects_sha_mismatch(self):
        with self.assertRaisesRegex(ValueError, "same SHA"):
            ExactHeadEvidence("a" * 40, "b" * 40, "a" * 40, "a" * 40, ("src/a.py",), ("ok",)).validate()

    def test_rejects_empty_diff(self):
        sha = "a" * 40
        with self.assertRaisesRegex(ValueError, "real diff"):
            ExactHeadEvidence(sha, sha, sha, sha, (), ("ok",)).validate()

    def test_rejects_unsafe_changed_path(self):
        sha = "a" * 40
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            ExactHeadEvidence(sha, sha, sha, sha, ("safe/../secret",), ("ok",)).validate()


if __name__ == "__main__":
    unittest.main()
