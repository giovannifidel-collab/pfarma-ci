from __future__ import annotations

import unittest

from razzo.kernel.continuation import ObjectiveCandidate, select_next_objective


class ContinuationTests(unittest.TestCase):
    def candidate(
        self,
        project: str,
        key: str,
        *,
        priority: int = 5,
        value: int = 5,
        risk: int = 1,
        domain: str | None = None,
        safe: bool = True,
    ) -> ObjectiveCandidate:
        return ObjectiveCandidate(
            project_id=project,
            objective_key=key,
            title=f"Objective {key}",
            priority=priority,
            product_value=value,
            risk=risk,
            collision_domains=(domain or key,),
            safe=safe,
        )

    def test_selects_highest_value_safe_candidate(self) -> None:
        decision = select_next_objective(
            [
                self.candidate("alpha", "a", priority=5, value=4),
                self.candidate("beta", "b", priority=5, value=8),
                self.candidate("gamma", "c", priority=9, value=10, safe=False),
            ],
            enabled_projects=("alpha", "beta", "gamma"),
        )
        self.assertEqual(decision.action, "SELECT")
        self.assertEqual(decision.candidate.objective_key, "b")

    def test_excludes_active_objective_and_collision(self) -> None:
        decision = select_next_objective(
            [
                self.candidate("alpha", "active", priority=10),
                self.candidate("beta", "colliding", priority=9, domain="inventory"),
                self.candidate("gamma", "safe", priority=3),
            ],
            enabled_projects=("alpha", "beta", "gamma"),
            active_objective_keys=("active",),
            active_collision_domains=("inventory",),
        )
        self.assertEqual(decision.candidate.objective_key, "safe")

    def test_disabled_projects_are_not_selected(self) -> None:
        decision = select_next_objective(
            [
                self.candidate("disabled", "high", priority=100),
                self.candidate("enabled", "normal", priority=1),
            ],
            enabled_projects=("enabled",),
        )
        self.assertEqual(decision.candidate.project_id, "enabled")

    def test_recently_served_project_loses_tie(self) -> None:
        decision = select_next_objective(
            [
                self.candidate("alpha", "a"),
                self.candidate("beta", "b"),
            ],
            enabled_projects=("alpha", "beta"),
            recently_served_projects=("alpha",),
        )
        self.assertEqual(decision.candidate.project_id, "beta")

    def test_waits_fail_closed_when_nothing_is_eligible(self) -> None:
        decision = select_next_objective(
            [self.candidate("alpha", "unsafe", safe=False)],
            enabled_projects=("alpha",),
        )
        self.assertEqual(decision.action, "WAIT")
        self.assertIsNone(decision.candidate)


if __name__ == "__main__":
    unittest.main()
