import unittest

from razzo.v7.product_discovery import (
    MAX_DISCOVERY_PAGES,
    MAX_LOGICAL_WORKER_POOL,
    collision_domain,
    issue_score,
    references_issue,
    risky,
)


class ProductDiscoveryTests(unittest.TestCase):
    def test_prioritizes_p0_high_bug(self):
        issue = {"title": "P0 operator bug", "body": "priority high; operational flow unusable"}
        self.assertGreaterEqual(issue_score(issue), 200)

    def test_human_gate_terms_fail_closed(self):
        for term in ("destructive-production", "user-data-write", "irreplaceable-data", "real-secrets", "irreversible-migration"):
            self.assertTrue(risky({"title": "task", "body": f"requires {term}"}), term)

    def test_implicit_real_data_gates_fail_closed(self):
        gated = (
            "explicit authorization before accessing or mutating real EasyFarm data",
            "requires a production write to inventory",
            "perform destructive repair of the live store",
            "mutate real data after approval",
        )
        for body in gated:
            self.assertTrue(risky({"title": "operational task", "body": body}), body)
        self.assertFalse(risky({"title": "P0 safe simulator", "body": "use fixtures only; no production writes"}))

    def test_open_pr_reference_blocks_duplicate_issue_dispatch(self):
        self.assertTrue(references_issue({"title": "Fix #152", "body": ""}, 152))
        self.assertTrue(references_issue({"title": "Fix", "body": "Closes #345"}, 345))
        self.assertFalse(references_issue({"title": "Fix #1520", "body": ""}, 152))

    def test_unscored_generic_issue_is_not_selected(self):
        self.assertEqual(issue_score({"title": "Documentation", "body": "minor note"}), 0)

    def test_collision_domain_prefers_explicit_module(self):
        issue = {"number": 10, "title": "P0 bug", "body": "Modulo: Nuova vendita\noperational bug"}
        self.assertEqual(collision_domain("pfarma-cloud", issue), "pfarma-cloud/module/nuova-vendita")

    def test_collision_domain_groups_related_work(self):
        a = {"number": 11, "title": "Catalogo prodotto EAN bug", "body": "high bug"}
        b = {"number": 12, "title": "MINSAN catalog search", "body": "P0 operational"}
        self.assertEqual(collision_domain("pfarma-cloud", a), "pfarma-cloud/catalog")
        self.assertEqual(collision_domain("pfarma-cloud", b), "pfarma-cloud/catalog")

    def test_elastic_pool_contract(self):
        self.assertEqual(MAX_LOGICAL_WORKER_POOL, 1000)
        self.assertGreaterEqual(MAX_DISCOVERY_PAGES, 10)


if __name__ == "__main__":
    unittest.main()
