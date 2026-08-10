#!/usr/bin/env python3
"""Regression tests for the fail-closed macrocycle validator."""

from __future__ import annotations

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

    def test_terminal_portfolio_has_no_execution_cursor(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
