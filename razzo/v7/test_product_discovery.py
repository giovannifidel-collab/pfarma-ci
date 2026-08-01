import json
import tempfile
import unittest
from pathlib import Path

from razzo.v7.actionability import fingerprint, validate
from razzo.v7.deterministic_discovery import discover
from razzo.v7.free_executor import execute
from razzo.v7.product_discovery import contains_unsafe_action, contract_from_issue, explicit_domain, references_issue


PROJECT = {
    "id": "project-giovanni",
    "repository": "giovannifidel-collab/project-giovanni",
    "integrationLane": "integration/razzo",
    "factoryTest": "npm run test:factory --if-present",
    "factoryPlan": "npm run factory:plan --if-present",
}
STATE = {"exactSha": "a" * 40}


def actionable_issue(number: int = 10) -> dict:
    return {
        "number": number,
        "title": "Complete resumable workout recovery journey",
        "body": """
## Product objective
Complete the interrupted workout recovery journey with deterministic resume state.

## User impact
A user can safely return to an interrupted workout without losing completed sets.

## Rationale
The current recovery path does not prove restored exercise position and elapsed state.

## Acceptance criteria
- Resume restores the last completed exercise and set.
- Resume preserves elapsed workout time after reload.

## Definition of Done
Both recovery behaviours are covered by regression tests and the registry-controlled product suites pass.

## Target surfaces
- src/workout/recovery.ts
- tests/workout/recovery.test.ts

## Expected product effect
Interrupted workouts resume at the correct position with preserved elapsed time.

## Collision domain
workout/resume-recovery

## Evidence required
- non-empty product diff
- registry-controlled tests green
- real product pull request

Safety boundary: no production writes and independent of user-data-write.
""",
    }


class ProductDiscoveryTests(unittest.TestCase):
    def test_keyword_only_issue_is_not_materialized(self):
        issue = {"number": 4, "title": "sales inventory accounting history ui", "body": "Improve these areas"}
        self.assertIsNone(contract_from_issue(PROJECT, STATE, issue))

    def test_complete_explicit_contract_is_materialized(self):
        item = contract_from_issue(PROJECT, STATE, actionable_issue())
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["collision_domain"], "project-giovanni/workout/resume-recovery")
        self.assertEqual(len(item["acceptance_criteria"]), 2)
        self.assertEqual(item["fingerprint"], fingerprint(item))
        self.assertEqual(validate(item), ("READY", []))

    def test_missing_target_surface_is_not_actionable(self):
        issue = actionable_issue()
        issue["body"] = issue["body"].replace("## Target surfaces\n- src/workout/recovery.ts\n- tests/workout/recovery.test.ts\n\n", "")
        self.assertIsNone(contract_from_issue(PROJECT, STATE, issue))

    def test_open_pr_overlap_is_rejected(self):
        item = contract_from_issue(PROJECT, STATE, actionable_issue(31))
        assert item is not None
        state, reasons = validate(item, open_pr_issue_numbers={31})
        self.assertEqual(state, "NOT_ACTIONABLE")
        self.assertIn("open_pr_overlap", reasons)

    def test_forbidden_target_path_is_rejected(self):
        item = contract_from_issue(PROJECT, STATE, actionable_issue(32))
        assert item is not None
        item["target_surfaces"] = [".github/workflows/unsafe.yml"]
        item["allowed_surfaces"] = list(item["target_surfaces"])
        item["fingerprint"] = fingerprint(item)
        state, reasons = validate(item)
        self.assertEqual(state, "NOT_ACTIONABLE")
        self.assertIn("target_overlaps_forbidden_surfaces", reasons)

    def test_safe_negations_do_not_trigger_risk_rejection(self):
        self.assertFalse(contains_unsafe_action("No production writes. Independent of destructive-production. Read-only."))
        self.assertTrue(contains_unsafe_action("Perform a production write to real customer data."))

    def test_explicit_domain_never_comes_from_keywords(self):
        self.assertEqual(explicit_domain("project-giovanni", "sales inventory accounting"), "")
        self.assertEqual(explicit_domain("project-giovanni", "Collision domain: workout/resume"), "project-giovanni/workout/resume")

    def test_pr_reference_matching_is_exact(self):
        self.assertTrue(references_issue({"title": "Fix #152", "body": ""}, 152))
        self.assertFalse(references_issue({"title": "Fix #1520", "body": ""}, 152))

    def test_project_giovanni_discovery_feeds_two_independent_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app").mkdir()
            (root / "package.json").write_text(json.dumps({"dependencies": {"next": "^15.2.4"}}), encoding="utf-8")
            payload = discover("project-giovanni", root)
            self.assertEqual(payload["engine"], "deterministic-free-v4")
            self.assertEqual(len(payload["candidates"]), 2)
            self.assertEqual(payload["suppressed_inflight"], [])
            self.assertEqual({item["collision_domain"] for item in payload["candidates"]}, {"product/global-error-recovery", "product/global-loading-feedback"})

    def test_project_giovanni_recipes_create_bounded_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app").mkdir()
            (root / "package.json").write_text("{}\n", encoding="utf-8")
            error_result = execute({"project_id":"project-giovanni","actionability_state":"READY","product_objective":"Add a bounded global application error recovery screen for Project Giovanni."}, root)
            loading_result = execute({"project_id":"project-giovanni","actionability_state":"READY","product_objective":"Add accessible global loading feedback for Project Giovanni route transitions."}, root)
            self.assertEqual(error_result["changed_files"], ["app/error.tsx"])
            self.assertEqual(loading_result["changed_files"], ["app/loading.tsx"])
            self.assertIn('"use client"', (root / "app" / "error.tsx").read_text(encoding="utf-8"))
            self.assertIn('aria-live="polite"', (root / "app" / "loading.tsx").read_text(encoding="utf-8"))

    def test_pfarma_discovery_feeds_two_non_colliding_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "api").mkdir()
            (root / "tests").mkdir()
            payload = discover("pfarma-cloud", root)
            self.assertEqual(payload["engine"], "deterministic-free-v4")
            self.assertEqual(len(payload["candidates"]), 2)
            self.assertEqual(
                {item["collision_domain"] for item in payload["candidates"]},
                {"inventory/stock-threshold-preview", "inventory/interwarehouse-transfer-preview"},
            )
            surfaces = [set(item["target_surfaces"]) for item in payload["candidates"]]
            self.assertTrue(surfaces[0].isdisjoint(surfaces[1]))

    def test_pfarma_recipes_create_modules_and_focused_tests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "api").mkdir()
            (root / "tests").mkdir()
            threshold = execute({"project_id":"pfarma-cloud","actionability_state":"READY","product_objective":"Add a read-only stock threshold preview that classifies urgent, low and healthy inventory without changing stock."}, root)
            transfer = execute({"project_id":"pfarma-cloud","actionability_state":"READY","product_objective":"Add a read-only E-to-A or A-to-E warehouse transfer preview with post-transfer balances and no inventory write."}, root)
            self.assertEqual(set(threshold["changed_files"]), {"api/stock_threshold_preview.py", "tests/test_stock_threshold_preview.py"})
            self.assertEqual(set(transfer["changed_files"]), {"api/interwarehouse_transfer_preview.py", "tests/test_interwarehouse_transfer_preview.py"})
            self.assertIn("production_write: bool = False", (root / "api" / "stock_threshold_preview.py").read_text(encoding="utf-8"))
            self.assertIn("insufficient source stock", (root / "api" / "interwarehouse_transfer_preview.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
