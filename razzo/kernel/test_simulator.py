from __future__ import annotations

import unittest

from .simulator import FaultProfile, run_campaign, simulate_once
from .testing import make_plan


class SimulatorTests(unittest.TestCase):
    def test_clean_simulation_completes(self):
        result = simulate_once(make_plan(), seed=1, fault_profile=FaultProfile(0, 0, 0, 0, 0))
        self.assertTrue(result.success)
        self.assertEqual(len(result.completed_nodes), 5)

    def test_duplicate_events_are_ignored(self):
        result = simulate_once(make_plan(), seed=2, fault_profile=FaultProfile(0, 1, 0, 0, 0))
        self.assertTrue(result.success)
        self.assertGreater(result.duplicate_events_ignored, 0)

    def test_stale_evidence_is_rejected_and_retried(self):
        result = simulate_once(make_plan(), seed=3, fault_profile=FaultProfile(0, 0, 0.2, 0.2, 0))
        self.assertTrue(result.success)
        self.assertGreaterEqual(result.rejected_stale_evidence, 0)

    def test_crash_replay_preserves_state(self):
        result = simulate_once(make_plan(), seed=4, fault_profile=FaultProfile(0, 0, 0, 0, 1))
        self.assertTrue(result.success)
        self.assertFalse(result.invariant_violations)

    def test_fault_profile_validates_range(self):
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            FaultProfile(node_failure_rate=2).validate()

    def test_campaign_has_no_invariant_failures(self):
        campaign = run_campaign(make_plan(), seeds=range(500), fault_profile=FaultProfile(0.04, 0.1, 0.03, 0.03, 0.1))
        self.assertEqual(campaign.failures, 0)
        self.assertFalse(campaign.invariant_failure_examples)
        self.assertGreater(campaign.total_retries, 0)

    def test_campaign_is_deterministic(self):
        kwargs = dict(seeds=range(50), fault_profile=FaultProfile(0.02, 0.05, 0.01, 0.01, 0.02))
        self.assertEqual(run_campaign(make_plan(), **kwargs), run_campaign(make_plan(), **kwargs))


if __name__ == "__main__":
    unittest.main()
