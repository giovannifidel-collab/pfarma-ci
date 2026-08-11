#!/usr/bin/env python3
"""Regression tests for the fail-closed macrocycle validator."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).with_name("validate_macrocycles.py")
SPEC = importlib.util.spec_from_file_location("validate_macrocycles", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MacrocycleValidatorTests(unittest.TestCase):
    def test_canonical_macrocycle_contract_is_valid(self) -> None:
        MODULE.validate()

    def test_expected_productive_ids_are_complete(self) -> None:
        self.assertEqual(MODULE.EXPECTED_IDS, {f"MC-{index:02d}" for index in range(1, 21)})

    def test_completed_is_not_an_allowed_active_state(self) -> None:
        self.assertIn("COMPLETED", MODULE.ALLOWED_STATES)
        self.assertNotIn("COMPLETED", MODULE.ACTIVE_STATES)

    def test_historical_terminal_portfolio_remains_60_of_60(self) -> None:
        state = MODULE.load_json(MODULE.STATE)
        self.assertTrue(state["terminal"])
        self.assertEqual(state["completedProductiveMacrocycles"], 60)
        for project in state["projects"]:
            self.assertTrue(project["terminal"])
            self.assertEqual(project["productiveMacrocyclesCompleted"], 20)
            self.assertEqual(project["completedThrough"], "MC-20")
            self.assertIsNone(project["active"])
            self.assertIsNone(project["next"])
            self.assertEqual(project["pendingHumanGates"], [])
            self.assertIn("MC-20", {item["id"] for item in project["completed"]})

    def test_terminal_state_requires_persisted_receipt(self) -> None:
        state = MODULE.load_json(MODULE.STATE)
        self.assertEqual(state["terminalReceipt"], "receipts/portfolio-60of60-completion.json")
        for project in state["projects"]:
            self.assertTrue(project["terminalReceipt"].startswith("receipts/"))

    def test_perfection_v1_closes_exactly_three_p01_cycles(self) -> None:
        state = MODULE.load_json(MODULE.PERFECTION_STATE)
        self.assertEqual(state["roadmap"], "PERFECTION_V1")
        self.assertEqual(state["baseRoadmap"], "COMPLETED_60_OF_60")
        self.assertTrue(state["historicalTerminalRoadmapUnchanged"])
        self.assertEqual(state["completedMacrocycles"], 3)
        expected = {
            "project-giovanni": "PG-P01",
            "pfarma-cloud": "PF-P01",
            "family-cloud": "FC-P01",
        }
        for project_id, cycle_id in expected.items():
            project = state["projects"][project_id]
            self.assertEqual(project["completed"][0]["id"], cycle_id)
            self.assertEqual(project["completed"][0]["status"], "COMPLETED")
            self.assertIsNone(project["active"])
            self.assertIsNone(project["next"])
            self.assertTrue((MODULE.ROOT / project["completed"][0]["receipt"]).is_file())

    def test_perfection_receipts_do_not_claim_independent_approval(self) -> None:
        state = MODULE.load_json(MODULE.PERFECTION_STATE)
        for project_id, project in state["projects"].items():
            receipt = MODULE.load_json(MODULE.receipt_path(project["completed"][0]["receipt"]))
            self.assertFalse(receipt["independentReviewerApproval"])

    def test_perfection_receipt_rejects_fabricated_independent_approval(self) -> None:
        state = MODULE.load_json(MODULE.PERFECTION_STATE)
        project = state["projects"]["project-giovanni"]
        item = project["completed"][0]
        receipt = MODULE.load_json(MODULE.receipt_path(item["receipt"]))
        tampered = copy.deepcopy(receipt)
        tampered["independentReviewerApproval"] = True
        with self.assertRaisesRegex(ValueError, "must not be fabricated"):
            MODULE.validate_perfection_receipt("project-giovanni", item["id"], project["lane"], tampered)

    def test_perfection_receipt_rejects_red_evidence(self) -> None:
        state = MODULE.load_json(MODULE.PERFECTION_STATE)
        project = state["projects"]["family-cloud"]
        item = project["completed"][0]
        receipt = MODULE.load_json(MODULE.receipt_path(item["receipt"]))
        tampered = copy.deepcopy(receipt)
        tampered["evidence"][0]["conclusion"] = "failure"
        with self.assertRaisesRegex(ValueError, "all evidence must be successful"):
            MODULE.validate_perfection_receipt("family-cloud", item["id"], project["lane"], tampered)

    def test_family_p01_requires_real_render_qa(self) -> None:
        state = MODULE.load_json(MODULE.PERFECTION_STATE)
        project = state["projects"]["family-cloud"]
        item = project["completed"][0]
        receipt = MODULE.load_json(MODULE.receipt_path(item["receipt"]))
        self.assertTrue(receipt["productSpecificQaRequired"])
        self.assertEqual(receipt["productSpecificQaKind"], "real-render-visual-qa")
        kinds = {e["kind"] for e in receipt["evidence"] if e["conclusion"] == "success"}
        self.assertIn("real-render-visual-qa", kinds)


if __name__ == "__main__":
    unittest.main()
