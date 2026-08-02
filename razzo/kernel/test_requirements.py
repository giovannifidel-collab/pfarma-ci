from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class CanonicalRequirementsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads((ROOT / "requirements.json").read_text(encoding="utf-8"))
        self.requirements = self.payload["requirements"]

    def test_schema_and_requirement_ids_are_unique(self) -> None:
        self.assertEqual(self.payload["schema"], "razzo-kernel-requirements-v1")
        ids = [item["id"] for item in self.requirements]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, [f"RZ-{index:03d}" for index in range(1, 21)])

    def test_every_requirement_is_traceable_and_testable(self) -> None:
        allowed_states = {"planned", "partial", "implemented", "verified"}
        for item in self.requirements:
            with self.subTest(requirement=item["id"]):
                self.assertTrue(item["name"].strip())
                self.assertTrue(item["component"].strip())
                self.assertGreaterEqual(len(item["acceptance"].strip()), 30)
                self.assertIn(item["state"], allowed_states)

    def test_permanent_safety_and_delivery_requirements_exist(self) -> None:
        names = {item["name"] for item in self.requirements}
        expected = {
            "Dynamic portfolio",
            "Live canonical state",
            "Delivery Objective identity",
            "Single canonical branch and PR",
            "Dynamic decomposition",
            "Bounded real parallelism",
            "Collision-safe leases",
            "Repository-local execution contract",
            "Builder isolation",
            "Objective assembly",
            "Product CI exact-head",
            "Independent functional QA",
            "Expected-head protection",
            "Truthful evidence",
            "Human gates are action-scoped",
            "Self-replan",
            "Event-driven continuation",
            "Multi-project fairness",
            "Private-source hygiene",
            "Operational proof",
        }
        self.assertEqual(names, expected)

    def test_operational_proof_remains_unverified_until_real_pilot(self) -> None:
        proof = next(item for item in self.requirements if item["id"] == "RZ-020")
        self.assertNotEqual(proof["state"], "verified")


if __name__ == "__main__":
    unittest.main()
