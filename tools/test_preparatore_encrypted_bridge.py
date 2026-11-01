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

    def test_chunk_round_trip_and_tampering_rejected(self):
        import base64
        import hashlib
        import json
        import sys
        from unittest.mock import patch
        sys.path.insert(0, str(Path("tools").resolve()))
        import download_preparatore_encrypted_worker as bridge

        sha = "a" * 40
        payload = json.dumps({"source_ref": sha, "format": "test", "payload": "x" * 12000}).encode()
        chunks = [payload[i:i+200] for i in range(0,len(payload),200)]
        manifest = {"v": 2, "source_ref": sha, "chunks": len(chunks),
                    "byte_length": len(payload), "bundle_sha256": hashlib.sha256(payload).hexdigest()}
        objects = {f"worker-source/chunks/{sha}/{i:03d}.json":
                   json.dumps({"v": 1, "source_ref": sha, "index": i,
                               "data_b64": base64.b64encode(chunk).decode()}).encode()
                   for i,chunk in enumerate(chunks)}
        with patch.object(bridge, "object_url", side_effect=lambda p:p):
            with patch.object(bridge, "fetch", side_effect=lambda p:objects.get(p)):
                self.assertEqual(bridge.verified_chunks(sha,manifest),payload)
                poisoned = dict(manifest, bundle_sha256="0"*64)
                with self.assertRaises(RuntimeError):
                    bridge.verified_chunks(sha,poisoned)

if __name__ == "__main__":
    unittest.main()
