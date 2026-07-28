import json
import tempfile
import unittest
from pathlib import Path

from tools.razzo_portfolio import (
    ProjectState,
    allocate_portfolio,
    load_reconciled_states,
    portfolio_decision,
    project_state_from_snapshot,
    project_state_from_task_graph,
)


class RazzoPortfolioTests(unittest.TestCase):
    def test_allocates_all_normal_slots_when_work_exists(self):
        states = [
            ProjectState("project-giovanni", ready=14, normal_concurrency=16, burst_concurrency=32),
            ProjectState("pfarma-cloud", ready=19, normal_concurrency=16, burst_concurrency=32),
            ProjectState("family-cloud", ready=11, normal_concurrency=32, burst_concurrency=128),
        ]
        allocation = allocate_portfolio(states, 32)
        self.assertEqual(sum(allocation.values()), 32)
        self.assertTrue(allocation["project-giovanni"])
        self.assertTrue(allocation["pfarma-cloud"])
        self.assertTrue(allocation["family-cloud"])

    def test_backpressure_redirects_capacity(self):
        states = [
            ProjectState("project-giovanni", ready=30, normal_concurrency=20, burst_concurrency=32),
            ProjectState("pfarma-cloud", ready=30, backpressure=True, normal_concurrency=16, burst_concurrency=32),
            ProjectState("family-cloud", ready=30, normal_concurrency=20, burst_concurrency=128),
        ]
        decision = portfolio_decision(states, 32)
        self.assertEqual(decision["allocation"]["pfarma-cloud"], 0)
        self.assertEqual(decision["allocated"], 32)
        self.assertEqual(decision["idle"], 0)

    def test_human_gate_does_not_block_other_projects(self):
        states = [
            ProjectState("project-giovanni", ready=4, human_gate=True, normal_concurrency=16, burst_concurrency=32),
            ProjectState("pfarma-cloud", ready=20, normal_concurrency=16, burst_concurrency=32),
            ProjectState("family-cloud", ready=20, normal_concurrency=20, burst_concurrency=128),
        ]
        decision = portfolio_decision(states, 24)
        self.assertEqual(decision["allocation"]["project-giovanni"], 0)
        self.assertEqual(decision["allocated"], 24)

    def test_self_replan_when_all_ready_work_is_gated(self):
        states = [
            ProjectState("project-giovanni", ready=2, human_gate=True),
            ProjectState("pfarma-cloud", ready=3, backpressure=True),
            ProjectState("family-cloud", ready=0),
        ]
        decision = portfolio_decision(states, 32)
        self.assertTrue(decision["selfReplan"])
        self.assertEqual(decision["replanReason"], "all-ready-work-gated")
        self.assertEqual(decision["allocated"], 0)

    def test_self_replan_when_safe_backlog_is_exhausted(self):
        states = [
            ProjectState("project-giovanni", ready=0, human_gate=True),
            ProjectState("pfarma-cloud", ready=0, human_gate=True),
            ProjectState("family-cloud", ready=0, human_gate=True),
        ]
        decision = portfolio_decision(states, 32)
        self.assertTrue(decision["safeBacklogExhausted"])
        self.assertTrue(decision["selfReplan"])
        self.assertEqual(decision["replanReason"], "safe-backlog-exhausted")
        self.assertEqual(decision["allocated"], 0)

    def test_derives_ready_work_from_task_graph(self):
        graph = {
            "tasks": [
                {"id": "A", "status": "done"},
                {"id": "B", "status": "ready"},
                {"id": "C", "status": "ready"},
                {"id": "D", "status": "blocked", "humanGate": "destructive-production"},
            ]
        }
        state = project_state_from_task_graph(
            "pfarma-cloud", graph, normal_concurrency=16, burst_concurrency=32
        )
        self.assertEqual(state.ready, 2)
        self.assertFalse(state.human_gate)
        self.assertEqual(state.runnable, 2)

    def test_derives_human_gate_when_only_blocked_sensitive_work_remains(self):
        graph = {
            "tasks": [
                {"id": "A", "status": "done"},
                {"id": "B", "status": "blocked", "humanGate": "user-data-write"},
            ]
        }
        state = project_state_from_task_graph(
            "project-giovanni", graph, normal_concurrency=16, burst_concurrency=32
        )
        self.assertEqual(state.ready, 0)
        self.assertTrue(state.human_gate)
        self.assertEqual(state.runnable, 0)

    def test_rejects_malformed_task_graph(self):
        with self.assertRaises(ValueError):
            project_state_from_task_graph(
                "family-cloud", {"tasks": "not-a-list"}, normal_concurrency=32, burst_concurrency=128
            )

    def test_snapshot_requires_exact_canonical_sha(self):
        project = {
            "id": "project-giovanni",
            "normalConcurrency": 16,
            "burstConcurrency": 32,
        }
        state = {
            "id": "project-giovanni",
            "exactSha": "a" * 40,
            "ready": 0,
            "backpressure": False,
            "humanGate": True,
        }
        with self.assertRaisesRegex(ValueError, "exact SHA mismatch"):
            project_state_from_snapshot(project, state, "b" * 40)

    def test_loads_reconciled_exact_ref_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "razzo").mkdir()
            sha_a = "a" * 40
            sha_b = "b" * 40
            (root / "razzo" / "a-ref.txt").write_text(sha_a + "\n", encoding="utf-8")
            (root / "b-ref.txt").write_text(sha_b + "\n", encoding="utf-8")
            snapshot = {
                "projects": [
                    {
                        "id": "a",
                        "exactSha": sha_a,
                        "ready": 2,
                        "backpressure": False,
                        "humanGate": False,
                    },
                    {
                        "id": "b",
                        "exactSha": sha_b,
                        "ready": 0,
                        "backpressure": False,
                        "humanGate": True,
                    },
                ]
            }
            (root / "razzo" / "project-state.json").write_text(
                json.dumps(snapshot), encoding="utf-8"
            )
            config = {
                "projects": [
                    {
                        "id": "a",
                        "normalConcurrency": 4,
                        "burstConcurrency": 8,
                        "portfolioRefFile": "razzo/a-ref.txt",
                    },
                    {
                        "id": "b",
                        "normalConcurrency": 2,
                        "burstConcurrency": 4,
                        "portfolioRefFile": "b-ref.txt",
                    },
                ]
            }
            states = load_reconciled_states(root, config)
            self.assertEqual([state.ready for state in states], [2, 0])
            self.assertFalse(states[0].human_gate)
            self.assertTrue(states[1].human_gate)


if __name__ == "__main__":
    unittest.main()
