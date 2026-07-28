import unittest

from tools.razzo_portfolio import ProjectState, allocate_portfolio, portfolio_decision


class RazzoPortfolioTests(unittest.TestCase):
    def test_allocates_all_normal_slots_when_work_exists(self):
        states = [
            ProjectState("project-giovanni", ready=14, normal_concurrency=16, burst_concurrency=32),
            ProjectState("pfarma-cloud", ready=19, normal_concurrency=16, burst_concurrency=32),
            ProjectState("family-cloud", ready=11, normal_concurrency=32, burst_concurrency=128),
        ]
        allocation = allocate_portfolio(states, 32)
        self.assertEqual(sum(allocation.values()), 32)
        self.assertGreater(allocation["project-giovanni"], 0)
        self.assertGreater(allocation["pfarma-cloud"], 0)
        self.assertGreater(allocation["family-cloud"], 0)

    def test_backpressure_redirects_capacity_to_other_projects(self):
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
        self.assertEqual(decision["allocated"], 0)


if __name__ == "__main__":
    unittest.main()
