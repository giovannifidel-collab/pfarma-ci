import unittest

from razzo.v7.autoscaler import ScaleInput
from razzo.v7.fabric import make_plan, matrix_json, receipt


class FabricTests(unittest.TestCase):
    def test_provider_cap_bounds_materialization(self):
        plan = make_plan(
            ScaleInput(queued=1000, running=64, completed=200, failed=0,
                       current_concurrency=64, normal_concurrency=16, burst_concurrency=128),
            provider_cap=32,
        )
        self.assertEqual(plan.desired_concurrency, 128)
        self.assertEqual(plan.materialized_workers, 32)
        self.assertEqual(len(plan.worker_ids), 32)
        self.assertEqual(len(set(plan.worker_ids)), 32)

    def test_backpressure_shrinks_materialization(self):
        plan = make_plan(
            ScaleInput(queued=1000, running=64, completed=100, failed=0,
                       current_concurrency=64, normal_concurrency=16, burst_concurrency=128,
                       backpressure=True),
            provider_cap=64,
        )
        self.assertLessEqual(plan.materialized_workers, 16)
        self.assertEqual(plan.action, "scale_down")

    def test_matrix_and_receipt_are_deterministic_and_exact_sha_bound(self):
        plan = make_plan(
            ScaleInput(queued=100, running=4, completed=20, failed=0,
                       current_concurrency=4, normal_concurrency=8, burst_concurrency=32),
            provider_cap=8,
        )
        self.assertEqual(plan.materialized_workers, 8)
        self.assertIn('"v7-worker-001"', matrix_json(plan))
        r1 = receipt("v7-worker-001", "a" * 40, "proof-001")
        r2 = receipt("v7-worker-001", "a" * 40, "proof-001")
        self.assertEqual(r1, r2)
        self.assertEqual(r1["exact_sha"], "a" * 40)
        self.assertEqual(r1["status"], "verified")


if __name__ == "__main__":
    unittest.main()
