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

    def test_human_gate_is_action_scoped_when_safe_ready_work_exists(self):
        states = [
            ProjectState("project-giovanni", ready=4, human_gate=True, normal_concurrency=16, burst_concurrency=32),
            ProjectState("pfarma-cloud", ready=20, normal_concurrency=16, burst_concurrency=32),
            ProjectState("family-cloud", ready=20, normal_concurrency=20, burst_concurrency=128),
        ]
        decision = portfolio_decision(states, 24)
        self.assertEqual(decision["allocation"]["project-giovanni"], 4)
        self.assertEqual(decision["allocated"], 24)
        self.assertFalse(decision["humanGateStopsPortfolio"])

    def test_proactive_replan_before_queue_exhaustion_when_below_fanout_target(self):
        states = [
            ProjectState("project-giovanni", ready=1, human_gate=True, gate_reason="user-data-write", normal_concurrency=20, burst_concurrency=300),
            ProjectState("pfarma-cloud", ready=1, human_gate=True, gate_reason="destructive-production", normal_concurrency=20, burst_concurrency=350),
            ProjectState("family-cloud", ready=1, human_gate=True, gate_reason="irreplaceable-data", normal_concurrency=24, burst_concurrency=350),
        ]
        decision = portfolio_decision(
            states,
            64,
            target_useful_workstreams=12,
            min_useful_workstreams=3,
        )
        self.assertEqual(decision["runnableTotal"], 3)
        self.assertEqual(decision["allocated"], 3)
        self.assertEqual(decision["fanoutDeficit"], 9)
        self.assertTrue(decision["proactiveExpansionRequested"])
        self.assertTrue(decision["selfReplan"])
        self.assertEqual(decision["replanReason"], "fanout-deficit")
        self.assertEqual(
            decision["expansionTargets"],
            ["project-giovanni", "pfarma-cloud", "family-cloud"],
        )

    def test_self_replan_when_ready_zero_and_gate_remains(self):
        states = [
            ProjectState("project-giovanni", ready=0, human_gate=True, gate_reason="user-data-write"),
            ProjectState("pfarma-cloud", ready=0, backpressure=True),
            ProjectState("family-cloud", ready=0),
        ]
        decision = portfolio_decision(states, 32)
        self.assertTrue(decision["selfReplan"])
        self.assertEqual(decision["replanReason"], "safe-expansion-around-human-gates")
        self.assertEqual(decision["replanMode"], "freeze-gated-branches-and-expand-safe-work")
        self.assertEqual(decision["safeExpansionTargets"], ["project-giovanni"])
        self.assertEqual(decision["frozenHumanGates"], {"project-giovanni": "user-data-write"})
        self.assertEqual(decision["allocated"], 0)

    def test_safe_expansion_when_all_projects_end_at_human_gates(self):
        states = [
            ProjectState("project-giovanni", ready=0, human_gate=True, gate_reason="user-data-write"),
            ProjectState("pfarma-cloud", ready=0, human_gate=True, gate_reason="destructive-production"),
            ProjectState("family-cloud", ready=0, human_gate=True, gate_reason="irreplaceable-data"),
        ]
        decision = portfolio_decision(states, 32)
        self.assertTrue(decision["safeBacklogExhausted"])
        self.assertTrue(decision["selfReplan"])
        self.assertTrue(decision["safeExpansionRequested"])
        self.assertFalse(decision["humanGateStopsPortfolio"])
        self.assertEqual(decision["replanReason"], "safe-expansion-around-human-gates")
        self.assertEqual(decision["safeExpansionTargets"], [
            "project-giovanni",
            "pfarma-cloud",
            "family-cloud",
        ])
        self.assertEqual(decision["allocated"], 0)

    def test_backpressured_human_gate_is_not_safe_expansion_target(self):
        states = [
            ProjectState(
                "pfarma-cloud",
                ready=0,
                human_gate=True,
                gate_reason="destructive-production",
                backpressure=True,
            )
        ]
        decision = portfolio_decision(states, 32)
        self.assertFalse(decision["safeExpansionRequested"])
        self.assertEqual(decision["safeExpansionTargets"], [])
        self.assertTrue(decision["selfReplan"])
        self.assertEqual(decision["replanReason"], "safe-backlog-exhausted")

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
        self.assertIsNone(state.gate_reason)
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
        self.assertEqual(state.gate_reason, "user-data-write")
        self.assertTrue(state.safe_expansion_candidate)
        self.assertEqual(state.runnable, 0)

    def test_snapshot_gate_marker_does_not_zero_safe_ready_queue(self):
        project = {
            "id": "project-giovanni",
            "normalConcurrency": 16,
            "burstConcurrency": 32,
        }
        state = {
            "id": "project-giovanni",
            "exactSha": "a" * 40,
            "ready": 3,
            "backpressure": False,
            "humanGate": True,
            "blocker": "user-data-write",
        }
        parsed = project_state_from_snapshot(project, state, "a" * 40)
        self.assertTrue(parsed.human_gate)
        self.assertEqual(parsed.runnable, 3)

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
            "blocker": "user-data-write",
        }
        with self.assertRaisesRegex(ValueError, "exact SHA mismatch"):
            project_state_from_snapshot(project, state, "b" * 40)

    def test_loads_reconciled_exact_ref_states_and_gate_reason(self):
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
                        "blocker": "destructive-production",
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
            self.assertEqual(states[1].gate_reason, "destructive-production")


if __name__ == "__main__":
    unittest.main()
