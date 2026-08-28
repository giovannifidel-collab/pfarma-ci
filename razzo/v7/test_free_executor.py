from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from razzo.v7.deterministic_discovery import discover_family_cloud
from razzo.v7.free_executor import execute


VAULT_CONTENT = "(()=>{const KEY='family-cloud.demo-vault-id';const VALID=/^fcv_[a-z0-9]{16,64}$/;let value=localStorage.getItem(KEY)||'';if(!VALID.test(value)){const bytes=new Uint8Array(12);crypto.getRandomValues(bytes);value='fcv_'+Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');localStorage.setItem(KEY,value);}document.documentElement.dataset.vaultId=value;window.familyCloudVaultId=value;})();\n"


class FamilyCloudExecutorIsolationTests(unittest.TestCase):
    def _root(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        web = root / "web"
        web.mkdir()
        (web / "index.html").write_text("<html><head></head><body>durable-home</body></html>\n", encoding="utf-8")
        (web / "alpha.html").write_text("<html><head></head><body>legacy-alpha</body></html>\n", encoding="utf-8")
        return temp, root

    def test_vault_identity_is_wired_only_to_legacy_alpha(self) -> None:
        temp, root = self._root()
        self.addCleanup(temp.cleanup)
        original_home = (root / "web" / "index.html").read_text(encoding="utf-8")
        contract = {
            "project_id": "family-cloud",
            "actionability_state": "READY",
            "product_objective": "Give the signed-in local alpha a stable browser-local demo vault identity that survives reloads without a remote account service.",
        }

        result = execute(contract, root)

        self.assertEqual(result["state"], "CHANGED")
        self.assertNotIn("web/index.html", result["changed_files"])
        self.assertIn("web/alpha.html", result["changed_files"])
        self.assertIn("web/vault-identity.js", result["changed_files"])
        self.assertEqual((root / "web" / "index.html").read_text(encoding="utf-8"), original_home)
        self.assertNotIn("vault-identity.js", original_home)
        self.assertIn("vault-identity.js", (root / "web" / "alpha.html").read_text(encoding="utf-8"))

    def test_satisfied_legacy_alpha_recipe_is_no_change(self) -> None:
        temp, root = self._root()
        self.addCleanup(temp.cleanup)
        web = root / "web"
        (web / "vault-identity.js").write_text(VAULT_CONTENT, encoding="utf-8")
        alpha = (web / "alpha.html").read_text(encoding="utf-8")
        (web / "alpha.html").write_text(alpha.replace("</body>", '  <script src="/vault-identity.js"></script>\n</body>'), encoding="utf-8")
        contract = {
            "project_id": "family-cloud",
            "actionability_state": "READY",
            "product_objective": "Give the signed-in local alpha a stable browser-local demo vault identity that survives reloads without a remote account service.",
        }

        result = execute(contract, root)

        self.assertEqual(result, {"state": "NO_CHANGE", "reason": "recipe_already_satisfied", "changed_files": []})
        candidates = discover_family_cloud(root)
        self.assertFalse(any(item["candidate_id"] == "free-local-vault-identity" for item in candidates))


if __name__ == "__main__":
    unittest.main()
