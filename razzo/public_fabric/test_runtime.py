import tempfile
import unittest
from pathlib import Path

from razzo.public_fabric.runtime import CONFIG, ReceiptVerifier, Lease, load, proof


class PublicFabricTests(unittest.TestCase):
    def test_configuration(self):
        cfg = load(CONFIG)
        self.assertEqual(cfg["targetFanout"], {"min": 12, "max": 20, "hardMax": 24})
        self.assertEqual(len(cfg["shards"]), 12)
        self.assertEqual(len(cfg["reserveShards"]), 12)
        self.assertEqual(len(cfg["shards"]) + len(cfg["reserveShards"]), 24)
        self.assertEqual(cfg["maxGenerationsPerTrigger"], 4)
        self.assertTrue(cfg["incrementalReplan"])
        self.assertEqual(cfg["speculativeRetry"], "p95")
        self.assertTrue(cfg["oneProductPrPerVerticalSlice"])

    def test_four_generation_proof(self):
        with tempfile.TemporaryDirectory() as td:
            result = proof(Path(td))
            self.assertEqual(result["generations"], 4)
            self.assertEqual(result["logicalWorkItems"], 48)
            self.assertEqual(result["configuredShards"], 12)
            self.assertTrue((Path(td) / "aggregate-cycle-receipt.json").exists())

    def test_receipt_identity(self):
        lease = Lease("c", 1, "w", "razzo-shard-0003", "p", "o/r", "integration/razzo", "a" * 40, "v", "d", "i", 1)
        receipt = {"cycleId": "c", "generation": 1, "workItemId": "w", "shard": "razzo-shard-0003", "status": "completed", "startedEpoch": 1, "endedEpoch": 2, "exactInputSha": "a" * 40}
        self.assertTrue(ReceiptVerifier().verify(receipt, lease)["ok"])


if __name__ == "__main__":
    unittest.main()
