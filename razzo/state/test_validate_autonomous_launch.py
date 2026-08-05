from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).with_name("validate_autonomous_launch.py")
SPEC = importlib.util.spec_from_file_location("validate_autonomous_launch", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AutonomousLaunchGateTests(unittest.TestCase):
    def test_launch_gate_is_green(self) -> None:
        result = MODULE.validate()
        self.assertEqual(result["status"], "RAZZO_AUTONOMOUS_FACTORY_LAUNCH_GATE_GREEN")
        self.assertEqual(result["controllers"], 5)
        self.assertGreaterEqual(result["projects"], 1)
        self.assertGreaterEqual(result["shards"], 12)
        self.assertTrue(result["lastVerifiedWave"].startswith("razzo-"))
        self.assertGreater(result["workflowRunId"], 0)


if __name__ == "__main__":
    unittest.main()
