import unittest
from pathlib import Path

class PreparatoreEncryptedBridgeContract(unittest.TestCase):
    def test_worker_has_no_private_checkout(self):
        workflow = Path(".github/workflows/preparatore-v2-dispatch-bridge.yml").read_text()
        self.assertIn("download_preparatore_encrypted_worker.py",workflow)
        self.assertNotIn("repository: giovannifidel-collab/project-giovanni",workflow)
        self.assertIn("rescue-queued",workflow)

    def test_authenticated_source_verification(self):
        source = Path("tools/download_preparatore_encrypted_worker.py").read_text()
        for phrase in ("derived_key", "source_ref", "workerSourceSha", "subprocess.run"):
            self.assertIn(phrase,source)

if __name__ == "__main__":
    unittest.main()
