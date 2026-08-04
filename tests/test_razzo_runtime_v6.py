import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from razzo.runtime_v6 import runtime


PROJECTS = [
    {"id": "a", "repository": "o/a", "enabled": True, "integrationLane": "integration/razzo"},
    {"id": "b", "repository": "o/b", "enabled": True, "integrationLane": "agent/bootstrap"},
]


class RuntimeV6Tests(unittest.TestCase):
    @patch.object(runtime, "enabled_projects", return_value=PROJECTS)
    @patch.object(runtime, "resolve_ref", return_value="a" * 40)
    @patch.object(runtime, "load_json", return_value={"protocolVersion": 6})
    def test_materializes_real_queue_contract(self, *_):
        plan = runtime.materialize(1, "cycle-test", 8)
        self.assertEqual(len(plan["items"]), 8)
        self.assertEqual({item["projectId"] for item in plan["items"]}, {"a", "b"})
        self.assertEqual(len({item["workItemId"] for item in plan["items"]}), 8)
        required = {
            "workItemId", "projectId", "generationId", "collisionDomain",
            "targetLane", "exactInputSha", "idempotencyKey", "status", "workerId",
        }
        for item in plan["items"]:
            self.assertTrue(required.issubset(item))

    def test_peak_concurrency_detects_overlap(self):
        receipts = [
            {"startedEpoch": 1.0, "endedEpoch": 4.0},
            {"startedEpoch": 2.0, "endedEpoch": 3.0},
            {"startedEpoch": 5.0, "endedEpoch": 6.0},
        ]
        self.assertEqual(runtime.peak_concurrency(receipts), 2)

    def test_verifier_rejects_duplicate_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = {
                "workItemId": "x", "generationId": "g1", "status": "completed",
                "exactInputSha": "a", "observedSha": "a", "projectId": "p",
                "startedEpoch": 1, "endedEpoch": 2,
            }
            (root / "a.json").write_text(json.dumps(receipt))
            (root / "b.json").write_text(json.dumps(receipt))
            with self.assertRaisesRegex(RuntimeError, "duplicate"):
                runtime.verify(root, "g1", root / "summary.json")

    @patch.object(runtime, "materialize", return_value={"generationId": "c-g2", "items": [{"workItemId": "y"}]})
    def test_replan_materializes_next_generation(self, mocked):
        plan = runtime.replan({"verified": True, "projects": ["a", "b"]}, "c", 2)
        self.assertEqual(plan["generationId"], "c-g2")
        mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
