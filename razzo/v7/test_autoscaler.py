import unittest

from razzo.v7.autoscaler import ScaleInput, decide, geometric_ramp


class AutoscalerTests(unittest.TestCase):
    def test_geometric_ramp_is_bounded(self):
        self.assertEqual(geometric_ramp(4, 128, 6), [4, 8, 16, 32, 64, 128])
        self.assertEqual(geometric_ramp(16, 64, 6), [16, 32, 64, 64, 64, 64])

    def test_queue_pressure_doubles_until_burst_cap(self):
        d = decide(ScaleInput(queued=100, running=4, completed=20, failed=0,
                              current_concurrency=4, normal_concurrency=16, burst_concurrency=128))
        self.assertEqual(d.desired_concurrency, 16)
        self.assertEqual(d.action, "scale_up")

        d2 = decide(ScaleInput(queued=1000, running=64, completed=200, failed=0,
                               current_concurrency=64, normal_concurrency=16, burst_concurrency=128))
        self.assertEqual(d2.desired_concurrency, 128)

    def test_backpressure_forces_scale_down(self):
        d = decide(ScaleInput(queued=1000, running=64, completed=100, failed=0,
                              current_concurrency=64, normal_concurrency=16, burst_concurrency=128,
                              backpressure=True))
        self.assertEqual(d.action, "scale_down")
        self.assertLessEqual(d.desired_concurrency, 16)

    def test_failure_rate_forces_scale_down(self):
        d = decide(ScaleInput(queued=1000, running=32, completed=70, failed=30,
                              current_concurrency=32, normal_concurrency=16, burst_concurrency=128))
        self.assertEqual(d.action, "scale_down")
        self.assertEqual(d.reason, "backpressure-or-failure-rate")

    def test_human_gate_only_queue_does_not_scale(self):
        d = decide(ScaleInput(queued=1000, running=0, completed=0, failed=0,
                              current_concurrency=32, normal_concurrency=16, burst_concurrency=128,
                              human_gate_only=True))
        self.assertEqual(d.desired_concurrency, 1)

    def test_idle_scales_to_one(self):
        d = decide(ScaleInput(queued=0, running=0, completed=0, failed=0,
                              current_concurrency=32, normal_concurrency=16, burst_concurrency=128))
        self.assertEqual(d.desired_concurrency, 1)
        self.assertEqual(d.reason, "idle")


if __name__ == "__main__":
    unittest.main()
