import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from razzo.v7.contract_materializer import extract_json_payload, materialize


PROJECT = {
    "id": "demo",
    "repository": "owner/demo",
    "integrationLane": "integration/razzo",
    "factoryTest": "python -m unittest",
    "factoryPlan": "python -m factory.plan",
}


class ContractMaterializerTests(unittest.TestCase):
    def make_repo(self) -> Path:
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
        (root / "app").mkdir()
        (root / "tests").mkdir()
        (root / "app" / "journey.py").write_text("VALUE = 1\n")
        (root / "tests" / "test_journey.py").write_text("pass\n")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "fixture"], cwd=root, check=True, capture_output=True)
        return root

    def candidate(self) -> dict:
        return {
            "candidate_id": "journey-1",
            "product_objective": "Allow a user to resume an interrupted local journey",
            "user_impact": "The user can continue without repeating completed steps.",
            "rationale": "The exact checkout already contains the journey state and focused tests.",
            "acceptance_criteria": [
                "Interrupted progress is restored after reopening the journey.",
                "The focused journey test proves the restored state.",
            ],
            "definition_of_done": "Implementation and focused regression test pass on the exact checkout.",
            "target_surfaces": ["app/journey.py", "tests/test_journey.py"],
            "expected_product_effect": "A previously interrupted journey resumes visibly.",
            "collision_domain": "journey/resume",
            "evidence_required": ["focused test output", "non-empty diff"],
            "dependencies": [],
        }

    def test_extracts_fenced_json(self):
        payload = extract_json_payload("result\n```json\n{\"candidates\": []}\n```")
        self.assertEqual(payload, {"candidates": []})

    def test_verified_candidate_becomes_ready(self):
        root = self.make_repo()
        result = materialize(
            json.dumps({"candidates": [self.candidate()]}),
            project=PROJECT,
            exact_sha="a" * 40,
            issue_number=12,
            issue_title="Journey",
            product_root=root,
        )
        self.assertEqual(len(result["ready"]), 1)
        item = result["ready"][0]
        self.assertEqual(item["actionability_state"], "READY")
        self.assertEqual(item["collision_domain"], "demo/journey/resume")
        self.assertEqual(item["required_tests"], [
            "python -m unittest",
            "python -m factory.plan",
        ])

    def test_nonexistent_surface_is_rejected(self):
        root = self.make_repo()
        candidate = self.candidate()
        candidate["target_surfaces"] = ["app/missing.py"]
        result = materialize(
            json.dumps([candidate]),
            project=PROJECT,
            exact_sha="b" * 40,
            issue_number=13,
            issue_title="Journey",
            product_root=root,
        )
        self.assertFalse(result["ready"])
        self.assertIn(
            "target_surface_not_verified_in_exact_checkout",
            result["rejected"][0]["reasons"],
        )

    def test_unsafe_candidate_is_rejected(self):
        root = self.make_repo()
        candidate = self.candidate()
        candidate["production_write"] = True
        result = materialize(
            json.dumps([candidate]),
            project=PROJECT,
            exact_sha="c" * 40,
            issue_number=14,
            issue_title="Journey",
            product_root=root,
        )
        self.assertFalse(result["ready"])
        self.assertIn("unsafe_candidate_capability", result["rejected"][0]["reasons"])


if __name__ == "__main__":
    unittest.main()
