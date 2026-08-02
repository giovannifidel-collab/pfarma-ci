from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from .canonical import ProjectContract
from .shadow import analyze_shadow, write_shadow_report
from .testing import make_plan


class ShadowTests(unittest.TestCase):
    def setUp(self):
        self.plan = make_plan()
        self.project = ProjectContract("pfarma-cloud", "giovannifidel-collab/pfarma-cloud", "integration/razzo", 5)

    def test_shadow_performs_no_mutations(self):
        report = analyze_shadow(self.plan, project=self.project)
        self.assertEqual(report.mode, "SHADOW")
        self.assertEqual(report.mutations_performed, 0)

    def test_shadow_returns_next_objective(self):
        report = analyze_shadow(self.plan, project=self.project)
        self.assertIsNotNone(report.next_wave_id)
        self.assertTrue(report.objective_branch.startswith("razzo/o/"))

    def test_shadow_completion_ratio(self):
        report = analyze_shadow(self.plan, project=self.project, completed_node_ids=("N001", "N002"))
        self.assertAlmostEqual(report.completion_ratio, 0.5)

    def test_shadow_reports_collision_block(self):
        report = analyze_shadow(self.plan, project=self.project, active_collision_domains=("inventory/schema",))
        self.assertIsNone(report.next_wave_id)
        self.assertTrue(report.warnings)

    def test_shadow_report_serializes(self):
        report = analyze_shadow(self.plan, project=self.project)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "report.json"
            write_shadow_report(report, path)
            self.assertIn(self.plan.capability_id, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
