from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from razzo.v7.shred_assembler import assemble
from razzo.v7.shred_planner import build_plan, validate_plan
from razzo.v7.shred_worker import ARTIFACTS


class ShredPipelineTests(unittest.TestCase):
    def test_plan_is_unique_dependency_safe_and_single_publish(self):
        plan = build_plan(repository="giovannifidel-collab/pfarma-cloud", exact_input_sha="a" * 40, integration_lane="integration/razzo")
        validate_plan(plan)
        self.assertEqual(len(plan["shreds"]), 6)
        self.assertTrue(plan["single_publish"])
        self.assertEqual(len({s["idempotency_key"] for s in plan["shreds"]}), 6)
        integrate = next(s for s in plan["shreds"] if s["shred_id"] == "S6-integrate")
        self.assertEqual(set(integrate["dependencies"]), {"S2-logic", "S3-safety", "S4-happy-tests", "S5-error-tests"})

    def test_assembler_requires_every_artifact_and_writes_one_objective(self):
        plan = build_plan(repository="repo", exact_input_sha="b" * 40, integration_lane="integration/razzo")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifacts = root / "artifacts"
            product = root / "product"
            artifacts.mkdir()
            for shred in plan["shreds"]:
                payload = {
                    "schema": "razzo-shred-artifact-v1",
                    "shred_id": shred["shred_id"],
                    "artifact": shred["artifact"],
                    "idempotency_key": shred["idempotency_key"],
                    "payload": ARTIFACTS[shred["artifact"]],
                }
                (artifacts / f"{shred['shred_id']}.json").write_text(json.dumps(payload), encoding="utf-8")
            changed = assemble(artifacts, product)
            self.assertEqual(changed, ["api/interwarehouse_transfer_preview.py", "tests/test_interwarehouse_transfer_preview.py"])
            self.assertEqual(assemble(artifacts, product), [])

    def test_duplicate_artifact_is_rejected(self):
        plan = build_plan(repository="repo", exact_input_sha="c" * 40, integration_lane="integration/razzo")
        shred = plan["shreds"][0]
        payload = {
            "schema": "razzo-shred-artifact-v1",
            "shred_id": shred["shred_id"],
            "artifact": shred["artifact"],
            "idempotency_key": shred["idempotency_key"],
            "payload": ARTIFACTS[shred["artifact"]],
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifacts = root / "artifacts"
            product = root / "product"
            artifacts.mkdir()
            (artifacts / "one.json").write_text(json.dumps(payload), encoding="utf-8")
            (artifacts / "two.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate shred artifact"):
                assemble(artifacts, product)


if __name__ == "__main__":
    unittest.main()
