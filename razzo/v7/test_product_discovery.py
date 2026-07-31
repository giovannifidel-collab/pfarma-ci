import unittest
from datetime import datetime, timedelta, timezone

from razzo.v7.actionability import fingerprint, validate
from razzo.v7.product_discovery import contract_from_issue, explicit_domain, references_issue


PROJECT = {
    "id": "project-giovanni",
    "repository": "giovannifidel-collab/project-giovanni",
    "integrationLane": "integration/razzo",
    "factoryTest": "npm test",
    "factoryPlan": "npm run factory:plan",
}
STATE = {"exactSha": "a" * 40}


def actionable_issue(number: int = 10) -> dict:
    return {
        "number": number,
        "title": "Complete resumable workout recovery journey",
        "body": """
Product objective: Complete the interrupted workout recovery journey with deterministic resume state.
User impact: A user can safely return to an interrupted workout without losing completed sets.
Rationale: The current recovery path does not prove restored exercise position and elapsed state.
Acceptance criteria:
- Resume restores the last completed exercise and set.
- Resume preserves elapsed workout time after reload.
Definition of Done: Both recovery behaviours are covered by regression tests and the full factory suite passes.
Target surfaces:
- src/workout/recovery.ts
- tests/workout/recovery.test.ts
Required tests:
- workout recovery regression suite
- full factory test
Expected product effect: Interrupted workouts resume at the correct position with preserved elapsed time.
Collision domain: workout/resume-recovery
Evidence required:
- non-empty product diff
- green recovery regression tests
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
        issue["body"] = issue["body"].replace("Target surfaces:\n- src/workout/recovery.ts\n- tests/workout/recovery.test.ts\n", "")
        self.assertIsNone(contract_from_issue(PROJECT, STATE, issue))

    def test_project_giovanni_rejects_pfarma_domain(self):
        item = contract_from_issue(PROJECT, STATE, actionable_issue())
        assert item is not None
        item["collision_domain"] = "project-giovanni/accounting"
        item["fingerprint"] = fingerprint(item)
        state, reasons = validate(item)
        self.assertEqual(state, "NOT_ACTIONABLE")
        self.assertIn("project_domain_incompatible", reasons)

    def test_open_pr_overlap_is_rejected(self):
        item = contract_from_issue(PROJECT, STATE, actionable_issue(31))
        assert item is not None
        state, reasons = validate(item, open_pr_issue_numbers={31})
        self.assertEqual(state, "NOT_ACTIONABLE")
        self.assertIn("open_pr_overlap", reasons)

    def test_active_cooldown_is_not_ready(self):
        item = contract_from_issue(PROJECT, STATE, actionable_issue(32))
        assert item is not None
        future = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
        state_payload = {"items": {item["fingerprint"]: {"cooldown_until": future, "last_outcome": "NO_ACTIONABLE_CHANGE"}}}
        state, reasons = validate(item, state=state_payload)
        self.assertEqual(state, "COOLDOWN")
        self.assertIn("cooldown", reasons)

    def test_explicit_domain_never_comes_from_keywords(self):
        self.assertEqual(explicit_domain("project-giovanni", "sales inventory accounting"), "")
        self.assertEqual(explicit_domain("project-giovanni", "Collision domain: workout/resume"), "project-giovanni/workout/resume")

    def test_pr_reference_matching_is_exact(self):
        self.assertTrue(references_issue({"title": "Fix #152", "body": ""}, 152))
        self.assertFalse(references_issue({"title": "Fix #1520", "body": ""}, 152))


if __name__ == "__main__":
    unittest.main()
