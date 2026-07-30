#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from razzo.super_factory.phase4_certifier import certify

SOURCE_SHA = "e08cece2e45fb548df70dda01ec1d089b3917299"


class Phase4CertifierTests(unittest.TestCase):
    def build(self, root: Path, count: int = 3) -> tuple[Path, Path, Path]:
        receipts = root / "receipts"
        receipts.mkdir()
        items = []
        for index in range(1, count + 1):
            execution = f"phase4-gen-0001-exec-{index:04d}"
            worker_sha = str(index) * 40
            shard = f"giovannifidel-collab/razzo-shard-{index:04d}"
            receipt = {
                "schema": "razzo.homo-novus.phase4-receipt.v1",
                "status": "HEALTHY",
                "verification_state": "REAL_WORK_EXACT_REF_VERIFIED",
                "execution_id": execution,
                "work_item_id": f"phase4-gen-0001-w{index}",
                "project_id": "homo-novus-control-plane",
                "generation_id": "phase4-gen-0001",
                "source_repository": "giovannifidel-collab/pfarma-ci",
                "input_sha": SOURCE_SHA,
                "target_path": f"file-{index}.txt",
                "output_sha256": str(index + 3) * 64,
                "collision_domain": f"phase4/domain-{index}",
                "idempotency_key": f"key-{index}",
                "shard_repository": shard,
                "worker_sha": worker_sha,
                "product_progress": False,
            }
            (receipts / f"{execution}.json").write_text(json.dumps(receipt), encoding="utf-8")
            items.append({
                "execution_id": execution,
                "shard_repository": shard,
                "worker_sha": worker_sha,
                "run_id": 1000 + index,
                "run_conclusion": "success",
                "artifact_id": 2000 + index,
                "artifact_digest": "sha256:" + str(index + 6) * 64,
            })
        evidence = root / "evidence.json"
        evidence.write_text(json.dumps({
            "schema": "razzo.homo-novus.phase4-evidence.v1",
            "project_id": "homo-novus-control-plane",
            "generation_id": "phase4-gen-0001",
            "source_repository": "giovannifidel-collab/pfarma-ci",
            "source_exact_sha": SOURCE_SHA,
            "items": items,
        }), encoding="utf-8")
        return receipts, evidence, root / "composition.json"

    def test_certifies_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            receipts, evidence, output = self.build(Path(temp))
            first = certify(receipts, evidence, output)
            second = certify(receipts, evidence, output)
            self.assertEqual(first["composition_sha256"], second["composition_sha256"])
            self.assertEqual(first["receipt_count"], 3)
            self.assertEqual(first["shard_count"], 3)
            self.assertEqual(first["verification_state"], "REAL_GENERATION_COMPOSED")
            self.assertFalse(first["product_progress"])

    def test_fails_closed_on_missing_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            receipts, evidence, output = self.build(Path(temp))
            next(receipts.glob("*.json")).unlink()
            with self.assertRaises(SystemExit):
                certify(receipts, evidence, output)

    def test_fails_closed_on_worker_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            receipts, evidence, output = self.build(Path(temp))
            path = next(receipts.glob("*.json"))
            receipt = json.loads(path.read_text())
            receipt["worker_sha"] = "a" * 40
            path.write_text(json.dumps(receipt))
            with self.assertRaises(SystemExit):
                certify(receipts, evidence, output)

    def test_fails_closed_on_product_progress_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            receipts, evidence, output = self.build(Path(temp))
            path = next(receipts.glob("*.json"))
            receipt = json.loads(path.read_text())
            receipt["product_progress"] = True
            path.write_text(json.dumps(receipt))
            with self.assertRaises(SystemExit):
                certify(receipts, evidence, output)


if __name__ == "__main__":
    unittest.main()
