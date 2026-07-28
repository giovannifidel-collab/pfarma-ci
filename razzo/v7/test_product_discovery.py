import unittest

from razzo.v7.product_discovery import issue_score, references_issue, risky


class ProductDiscoveryTests(unittest.TestCase):
    def test_prioritizes_p0_high_bug(self):
        issue = {"title": "P0 operator bug", "body": "priority high; operational flow unusable"}
        self.assertGreaterEqual(issue_score(issue), 200)

    def test_human_gate_terms_fail_closed(self):
        for term in ("destructive-production", "user-data-write", "irreplaceable-data", "real-secrets", "irreversible-migration"):
            self.assertTrue(risky({"title": "task", "body": f"requires {term}"}), term)

    def test_open_pr_reference_blocks_duplicate_issue_dispatch(self):
        self.assertTrue(references_issue({"title": "Fix #152", "body": ""}, 152))
        self.assertTrue(references_issue({"title": "Fix", "body": "Closes #345"}, 345))
        self.assertFalse(references_issue({"title": "Fix #1520", "body": ""}, 152))

    def test_unscored_generic_issue_is_not_selected(self):
        self.assertEqual(issue_score({"title": "Documentation", "body": "minor note"}), 0)


if __name__ == "__main__":
    unittest.main()
