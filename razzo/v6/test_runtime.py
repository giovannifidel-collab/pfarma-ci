from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from razzo.v6.runtime import Runtime, WorkItem, proof_queue


class RazzoV6RuntimeTests(unittest.TestCase):
    def test_operational_proof_has_at_least_eight_independent_items(self):
        items = proof_queue()
        self.assertGreaterEqual(len(items), 8)
        self.assertEqual(len({x.workItemId for x in items}), len(items))
        self.assertEqual(len({x.idempotencyKey for x in items}), len(items))
        self.assertTrue(all(x.humanGate is None for x in items))

    def test_dispatch_produces_verified_receipts_and_real_concurrency(self):
        rt = Runtime(proof_queue(), concurrency=4)
        receipts = rt.dispatch()
        self.assertGreaterEqual(len(receipts), 4)
        self.assertTrue(all(x.status == "completed" for x in receipts))
        self.assertTrue(all(x.verification_state == "verified" for x in receipts))
        self.assertGreaterEqual(rt.concurrent_peak, 2)
        self.assertEqual(len({x.work_item_id for x in receipts}), len(receipts))

    def test_collision_domain_prevents_double_lease(self):
        base = proof_queue()[0]
        other = WorkItem(**{**asdict(base), "workItemId": "collision-copy", "idempotencyKey": "collision-copy-key"})
        rt = Runtime([base, other], concurrency=2)
        receipts = rt.dispatch()
        self.assertEqual(len(receipts), 1)
        self.assertEqual(sum(x.status == "queued" for x in rt.items.values()), 1)

    def test_human_gate_blocks_only_gated_item(self):
        a, b = proof_queue()[:2]
        a.humanGate = "irreplaceable-data"
        rt = Runtime([a, b], concurrency=2)
        receipts = rt.dispatch()
        self.assertEqual(a.status, "blocked")
        self.assertEqual(len(receipts), 1)
        self.assertEqual(b.status, "verified")

    def test_prior_verified_receipt_enforces_idempotency(self):
        item = proof_queue()[0]
        first = Runtime([item], concurrency=1)
        receipt = first.dispatch()[0]
        fresh = proof_queue()[0]
        second = Runtime([fresh], concurrency=1, prior_receipts=[receipt])
        receipts = second.dispatch()
        self.assertEqual(len(receipts), 1)
        self.assertEqual(fresh.status, "verified")

    def test_generation_does_not_promote_operational_proof(self):
        rt = Runtime(proof_queue(), concurrency=4)
        rt.dispatch()
        cycle = rt.aggregate("proof", 1, product_progress=False)
        self.assertFalse(cycle["generation_promoted"])
        self.assertFalse(cycle["product_progress"])
        self.assertFalse(cycle["duplicate_execution"])


if __name__ == "__main__":
    unittest.main()
