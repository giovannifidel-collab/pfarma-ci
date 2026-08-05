from __future__ import annotations

import unittest

from razzo.kernel.autonomous_launch import validate


class AutonomousLaunchGateTests(unittest.TestCase):
    def test_launch_gate_is_green(self) -> None:
        result = validate()
        self.assertEqual(result["status"], "RAZZO_AUTONOMOUS_FACTORY_LAUNCH_GATE_GREEN")
        self.assertEqual(result["controllers"], 5)
        self.assertGreaterEqual(result["projects"], 1)
        self.assertGreaterEqual(result["shards"], 12)
        self.assertTrue(result["lastVerifiedWave"].startswith("razzo-"))
        self.assertGreater(result["workflowRunId"], 0)


if __name__ == "__main__":
    unittest.main()
