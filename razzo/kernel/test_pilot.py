from __future__ import annotations

import unittest

from .pilot import fixture_plan, run_protected_pilot


class PilotTests(unittest.TestCase):
    def test_fixture_plan_has_five_nodes(self):
        self.assertEqual(len(fixture_plan().nodes), 5)

    def test_protected_pilot_is_non_mutating(self):
        report = run_protected_pilot(simulation_runs=100)
        self.assertTrue(report.fixture_only)
        self.assertFalse(report.product_writes_allowed)
        self.assertFalse(report.merge_allowed)
        self.assertEqual(report.shadow_mutations, 0)

    def test_protected_pilot_gates_green(self):
        report = run_protected_pilot(simulation_runs=200)
        self.assertEqual(report.activation_status, "PRELAUNCH_GATES_GREEN")
        self.assertEqual(report.simulation_failures, 0)

    def test_protected_pilot_rejects_invalid_run_count(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            run_protected_pilot(simulation_runs=0)


if __name__ == "__main__":
    unittest.main()
