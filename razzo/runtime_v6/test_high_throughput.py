import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from razzo.runtime_v6.high_throughput import CONFIG, load, preflight
from razzo.runtime_v6.high_throughput_runtime import run_cycle


class HighThroughputTests(unittest.TestCase):
    def test_required_configuration(self):
        cfg = load(CONFIG)
        self.assertEqual(cfg["fanout"]["targetMin"], 12)
        self.assertEqual(cfg["fanout"]["targetMax"], 20)
        self.assertEqual(cfg["fanout"]["hardMax"], 24)
        self.assertEqual(cfg["fanout"]["builderPerRepoMax"], 8)
        self.assertEqual(cfg["fanout"]["verifierMax"], 4)
        self.assertEqual(cfg["fanout"]["integratorPerCollisionDomain"], 1)
        self.assertEqual(cfg["fanout"]["queueRefillThreshold"], 8)
        self.assertEqual(cfg["generations"]["maxPerTrigger"], 4)
        self.assertTrue(cfg["generations"]["incrementalReplan"])
        self.assertEqual(cfg["retry"]["strategy"], "speculative-p95")
        self.assertTrue(cfg["receipts"]["perJob"])
        self.assertTrue(cfg["receipts"]["aggregate"])
        self.assertTrue(cfg["pullRequests"]["onePerVerticalSlice"])

    def test_product_preflight_fails_closed_without_external_prerequisites(self):
        with patch.dict("os.environ", {}, clear=True):
            result = preflight("product")
        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"]["writeToken"])
        self.assertFalse(result["checks"]["builderCommand"])
        self.assertFalse(result["checks"]["persistentRunner"])

    @patch("razzo.runtime_v6.high_throughput.Planner._ref", return_value="a" * 40)
    def test_proof_cycle_four_generations_and_receipts(self, _):
        with tempfile.TemporaryDirectory() as td:
            result = run_cycle("proof", Path(td))
            self.assertEqual(result["generations"], 4)
            self.assertGreaterEqual(result["logicalWorkItems"], 48)
            self.assertGreaterEqual(result["parallelPeak"], 2)
            self.assertGreaterEqual(result["receipts"], result["verified"])
            self.assertLessEqual(result["speculativeRetries"], result["logicalWorkItems"])
            self.assertTrue((Path(td) / "aggregate-cycle-receipt.json").exists())


if __name__ == "__main__":
    unittest.main()
