from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from razzo.kernel.controller import (
    ExistingObjectivePR,
    decide,
    load_projects,
    objective_from_payload,
)


BASE_SHA = "a" * 40


def objective_payload() -> dict:
    return {
        "project_id": "pfarma-cloud",
        "base_sha": BASE_SHA,
        "goal": "Add a safe stock preview",
        "user_outcome": "The operator can inspect stock without mutating data",
        "acceptance_criteria": [
            "Preview is read only",
            "Existing stock tests remain green",
        ],
        "collision_domains": ["api/stock", "tests/stock"],
        "shreds": [
            {
                "shred_id": "S01",
                "responsibility": "Implement the read-only service",
                "allowed_surfaces": ["api/stock.py"],
                "acceptance_subset": ["Preview is read only"],
                "collision_domain": "api/stock",
            },
            {
                "shred_id": "S02",
                "responsibility": "Add focused regression tests",
                "dependencies": ["S01"],
                "allowed_surfaces": ["tests/test_stock.py"],
                "acceptance_subset": ["Existing stock tests remain green"],
                "collision_domain": "tests/stock",
            },
        ],
    }


class ControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name, "projects.json")
        path.write_text(
            json.dumps(
                {
                    "projects": [
                        {
                            "id": "pfarma-cloud",
                            "repository": "giovannifidel-collab/pfarma-cloud",
                            "enabled": True,
                            "integrationLane": "integration/razzo",
                            "normalConcurrency": 20,
                            "protectMain": True,
                        },
                        {
                            "id": "disabled",
                            "repository": "org/disabled",
                            "enabled": False,
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.projects = load_projects(path)

    def objective(self):
        return objective_from_payload(objective_payload(), projects=self.projects)

    def test_registry_caps_builders_at_five(self) -> None:
        self.assertEqual(self.projects["pfarma-cloud"].max_builders, 5)

    def test_unknown_and_disabled_projects_fail_closed(self) -> None:
        payload = objective_payload()
        payload["project_id"] = "missing"
        with self.assertRaises(ValueError):
            objective_from_payload(payload, projects=self.projects)
        payload["project_id"] = "disabled"
        with self.assertRaises(ValueError):
            objective_from_payload(payload, projects=self.projects)

    def test_new_objective_uses_one_canonical_branch(self) -> None:
        objective = self.objective()
        decision = decide(objective, live_integration_head=BASE_SHA)
        self.assertEqual(decision.action, "CREATE_OBJECTIVE_BRANCH")
        self.assertEqual(decision.objective.branch, f"razzo/o/{objective.fingerprint[:20]}")

    def test_existing_canonical_pr_is_resumed(self) -> None:
        objective = self.objective()
        existing = ExistingObjectivePR(
            number=7,
            head=objective.branch,
            base=objective.integration_lane,
            state="open",
            fingerprint=objective.fingerprint,
        )
        decision = decide(objective, existing_prs=[existing], live_integration_head=BASE_SHA)
        self.assertEqual(decision.action, "RESUME_EXISTING")
        self.assertEqual(decision.existing_pr_number, 7)

    def test_duplicate_prs_block_execution(self) -> None:
        objective = self.objective()
        existing = ExistingObjectivePR(
            number=7,
            head=objective.branch,
            base=objective.integration_lane,
            state="open",
            fingerprint=objective.fingerprint,
        )
        decision = decide(
            objective,
            existing_prs=[existing, ExistingObjectivePR(**{**existing.__dict__, "number": 8})],
            live_integration_head=BASE_SHA,
        )
        self.assertEqual(decision.action, "BLOCKED_DUPLICATE_PR")

    def test_stale_base_requires_replan(self) -> None:
        decision = decide(self.objective(), live_integration_head="b" * 40)
        self.assertEqual(decision.action, "NEEDS_REPLAN")

    def test_noncanonical_existing_pr_blocks(self) -> None:
        objective = self.objective()
        existing = ExistingObjectivePR(
            number=9,
            head="razzo/wrong",
            base=objective.integration_lane,
            state="open",
            fingerprint=objective.fingerprint,
        )
        decision = decide(objective, existing_prs=[existing], live_integration_head=BASE_SHA)
        self.assertEqual(decision.action, "BLOCKED_CANONICAL_MISMATCH")


if __name__ == "__main__":
    unittest.main()
