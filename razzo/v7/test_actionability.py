from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from razzo.v7.actionability import fingerprint, record_outcome, validate


class ActionabilityTests(unittest.TestCase):
    def item(self) -> dict:
        item = {
            "work_item_id": "PG-UPLOAD-001",
            "fingerprint": "",
            "project_id": "project-giovanni",
            "repository": "giovannifidel-collab/project-giovanni",
            "issue_number": 147,
            "product_objective": "Allow a signed-in user to resume an interrupted photo upload",
            "user_impact": "Users can complete a real upload after a transient interruption.",
            "rationale": "The existing upload journey can be interrupted without a recovery action.",
            "acceptance_criteria": [
                "A retry action resumes the selected interrupted upload.",
                "A completed retry appears in the user's upload history.",
            ],
            "definition_of_done": "The recovery journey is implemented and its focused regression tests pass.",
            "target_surfaces": ["src/photo-upload.ts", "tests/photo-upload.test.ts"],
            "required_tests": ["npm test -- photo-upload"],
            "expected_product_effect": "Interrupted photo uploads can be completed without restarting the journey.",
            "collision_domain": "project-giovanni/photo-upload-recovery",
            "exact_input_sha": "a" * 40,
            "integration_lane": "main",
            "allowed_surfaces": ["src/photo-upload.ts", "tests/photo-upload.test.ts"],
            "forbidden_surfaces": [".github/workflows", "secrets"],
            "dependencies": [],
            "risk_class": "safe-product",
            "human_gate": False,
            "evidence_required": ["non-empty diff", "focused tests green", "product PR"],
        }
        item["fingerprint"] = fingerprint(item)
        return item

    def test_complete_contract_is_ready(self) -> None:
        state, reasons = validate(self.item(), state={"items": {}})
        self.assertEqual("READY", state)
        self.assertEqual([], reasons)

    def test_project_domain_mismatch_is_rejected(self) -> None:
        item = self.item()
        item["collision_domain"] = "project-giovanni/accounting"
        item["fingerprint"] = fingerprint(item)
        state, reasons = validate(item)
        self.assertEqual("NOT_ACTIONABLE", state)
        self.assertIn("project_domain_incompatible", reasons)

    def test_no_change_escalates_6h_24h_then_rediscovery(self) -> None:
        item = self.item()
        state = {"version": 1, "items": {}}
        now = datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)

        first = record_outcome(state, item, outcome="NO_ACTIONABLE_CHANGE", run_id="1", now=now)
        self.assertEqual("NO_ACTIONABLE_CHANGE", first["last_outcome"])
        self.assertEqual((now + timedelta(hours=6)).isoformat().replace("+00:00", "Z"), first["cooldown_until"])

        second = record_outcome(state, item, outcome="NO_ACTIONABLE_CHANGE", run_id="2", now=now + timedelta(hours=7))
        self.assertEqual("NO_ACTIONABLE_CHANGE", second["last_outcome"])
        self.assertEqual((now + timedelta(hours=31)).isoformat().replace("+00:00", "Z"), second["cooldown_until"])

        third = record_outcome(state, item, outcome="NO_ACTIONABLE_CHANGE", run_id="3", now=now + timedelta(hours=32))
        self.assertEqual("REQUIRES_REDISCOVERY", third["last_outcome"])
        self.assertIsNone(third["cooldown_until"])

        validation_state, reasons = validate(item, state=state, now=now + timedelta(hours=33))
        self.assertEqual("NEEDS_DEEPER_DISCOVERY", validation_state)
        self.assertIn("requires_rediscovery", reasons)

    def test_delivery_resets_no_change_streak(self) -> None:
        item = self.item()
        state = {"version": 1, "items": {}}
        now = datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)
        record_outcome(state, item, outcome="NO_ACTIONABLE_CHANGE", run_id="1", now=now)
        delivered = record_outcome(
            state,
            item,
            outcome="PRODUCT_DELIVERED",
            run_id="2",
            now=now + timedelta(hours=7),
            candidate_sha="b" * 40,
            pr_number=123,
            integration_state="pr_open",
        )
        self.assertEqual(0, delivered["consecutive_no_actionable_change"])
        self.assertIsNone(delivered["cooldown_until"])
        self.assertEqual(123, delivered["pr_number"])


if __name__ == "__main__":
    unittest.main()
