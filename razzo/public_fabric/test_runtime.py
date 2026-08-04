import tempfile
import unittest
from pathlib import Path

from razzo.public_fabric.runtime import CONFIG, PROJECTS, FabricPlanner, Lease, ReceiptVerifier, load, proof


class PublicFabricV8Tests(unittest.TestCase):
    def test_configuration_and_registry(self):
        cfg = load(CONFIG)
        registry = load(PROJECTS)
        self.assertEqual(cfg["version"], 8)
        self.assertEqual(cfg["targetFanout"], {"min": 12, "max": 20, "hardMax": 24})
        self.assertEqual(len(cfg["shards"]), 12)
        enabled = [p for p in registry["projects"] if p.get("enabled", True)]
        self.assertEqual(len(enabled), 3)
        self.assertTrue(all(len(p.get("publicFabricWorkstreams", [])) >= 4 for p in enabled))

    def test_operational_proof_materializes_real_wave(self):
        with tempfile.TemporaryDirectory() as td:
            result = proof(Path(td))
            self.assertEqual(result["logicalWorkItems"], 12)
            self.assertEqual(len(result["projects"]), 3)
            self.assertEqual(result["status"], "green")
            self.assertTrue((Path(td) / "leases.json").exists())
            self.assertTrue((Path(td) / "aggregate-cycle-receipt.json").exists())

    def test_unique_leases_and_collision_domains(self):
        cfg = load(CONFIG)
        projects = [p for p in load(PROJECTS)["projects"] if p.get("enabled", True)]
        refs = {p["id"]: "a" * 40 for p in projects}
        leases = FabricPlanner(cfg).materialize("cycle-test", 1, refs)
        self.assertEqual(len(leases), 12)
        self.assertEqual(len({x.workItemId for x in leases}), 12)
        self.assertEqual(len({x.idempotencyKey for x in leases}), 12)
        self.assertEqual(len({x.collisionDomain for x in leases}), 12)
        self.assertEqual(len({x.shard for x in leases}), 12)
        self.assertTrue(all(x.status == "leased" for x in leases))
        self.assertTrue(all(x.leaseExpiresEpoch > x.leasedEpoch for x in leases))
        self.assertTrue(all(not x.humanGate for x in leases))

    def test_receipt_verifier_requires_exact_observed_sha(self):
        lease = Lease(
            cycleId="c",
            generation=1,
            generationId="c-g1",
            workItemId="w",
            shard="razzo-shard-0003",
            projectId="p",
            repository="o/r",
            targetLane="integration/razzo",
            exactInputSha="a" * 40,
            title="verify",
            kind="verification",
            priority="P0",
            dependencies=(),
            verticalSlice="verify",
            collisionDomain="p:verify",
            verification="exact-sha",
            humanGate=None,
            idempotencyKey="i",
            status="leased",
            leasedEpoch=1.0,
            leaseExpiresEpoch=100.0,
            attempt=1,
            maxAttempts=2,
            commands=("git status --short",),
        )
        receipt = {
            "cycleId": "c",
            "generation": 1,
            "generationId": "c-g1",
            "workItemId": "w",
            "shard": "razzo-shard-0003",
            "projectId": "p",
            "status": "completed",
            "startedEpoch": 2,
            "endedEpoch": 3,
            "exactInputSha": "a" * 40,
            "observedSha": "a" * 40,
        }
        self.assertTrue(ReceiptVerifier().verify(receipt, lease)["ok"])
        bad = dict(receipt, observedSha="b" * 40)
        self.assertFalse(ReceiptVerifier().verify(bad, lease)["ok"])


if __name__ == "__main__":
    unittest.main()
