"""Offline unit tests for strict, isolated social ciphertext validation."""
from __future__ import annotations
import base64
import json
import tempfile
import unittest
from pathlib import Path

from validate_social_bundle import validate_bundle


class SocialBundleValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "bundle.json"
        self.payload = {
            "format":"PFARMA_CI_BUNDLE_V2",
            "algorithm":"AES-256-GCM",
            "source_ref":"a"*40,
            "file_count":28,
            "plaintext_sha256":"b"*64,
            "nonce_b64":base64.b64encode(b"n"*12).decode(),
            "ciphertext_b64":base64.b64encode(b"c"*32).decode()
        }

    def write(self):
        self.path.write_text(json.dumps(self.payload), encoding="utf-8")

    def test_well_formed_envelope(self):
        self.write()
        self.assertEqual(validate_bundle(self.path)["file_count"], 28)

    def test_reject_plaintext(self):
        self.path.write_text("print('secret')", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            validate_bundle(self.path)

    def test_reject_extra_credentials(self):
        self.payload["access_token"] = "NOT_AN_ACTUAL_TOKEN"
        self.write()
        with self.assertRaisesRegex(ValueError, "schema"):
            validate_bundle(self.path)

    def test_reject_no_authentication_tag(self):
        self.payload["ciphertext_b64"] = base64.b64encode(b"x"*12).decode()
        self.write()
        with self.assertRaisesRegex(ValueError, "tag"):
            validate_bundle(self.path)

    def test_reject_invalid_nonce(self):
        self.payload["nonce_b64"] = base64.b64encode(b"x"*8).decode()
        self.write()
        with self.assertRaisesRegex(ValueError, "12 bytes"):
            validate_bundle(self.path)

    def test_reject_wrong_cipher(self):
        self.payload["algorithm"] = "AES-CTR"
        self.write()
        with self.assertRaisesRegex(ValueError, "AES-256-GCM"):
            validate_bundle(self.path)

    def test_reject_non_hex_commit(self):
        self.payload["source_ref"] = "../../main"
        self.write()
        with self.assertRaisesRegex(ValueError, "commit"):
            validate_bundle(self.path)


if __name__ == "__main__":
    unittest.main()
