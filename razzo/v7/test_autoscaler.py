import unittest

from razzo.v7.autoscaler import ScaleInput, decide, geometric_ramp


class AutoscalerTests(unittest.TestCase):
    def test_geometric_ramp_is_bounded(self):
        self.assertEqual(geometric_ramp(4, 128, 6), [4, 8, 16, 32, 64, 128])
        self.assertEqual(geometric_ramp(16, 64, 6), [16, 32, 64, 64, 64, 64])
        self.assertEqual(geometric_ramp(32, 220, 5), [32, 64, 128, 220, 220])

    def test_queue_pressure_doubles_until_burst_cap(self):
        d = decide(ScaleInput(queued=100, running=4, completed=20, failed=0,
                              current_concurrency=4, normal_concurrency=16, burst_concurrency=128))
        self.assertEqual(d.desired_concurrency, 16)
        self.assertEqual(d.action, "scale_up")

        d2 = decide(ScaleInput(queued=1000, running=64, completed=200, failed=0,
                               current_concurrency=64, normal_concurrency=16, burst_concurrency=128))
        self.assertEqual(d2.desired_concurrency, 128)

        d3 = decide(ScaleInput(queued=10000, running=128, completed=1000, failed=0,
                               current_concurrency=128, normal_concurrency=32, burst_concurrency=220))
        self.assertEqual(d3.desired_concurrency, 220)
        self.assertEqual(d3.action, "scale_up")

    def test_provider_cap_is_lower_than_registry_burst(self):
        d = decide(ScaleInput(queued=10000, running=180, completed=1000, failed=0,
                              current_concurrency=180, normal_concurrency=64,
                              burst_concurrency=1000, provider_cap=140))
        self.assertEqual(d.desired_concurrency, 140)
        self.assertEqual(d.action, "scale_down")
        self.assertEqual(d.reason, "provider-cap")

    def test_provider_cap_blocks_blind_scale_up(self):
        d = decide(ScaleInput(queued=10000, running=64, completed=1000, failed=0,
                              current_concurrency=64, normal_concurrency=64,
                              burst_concurrency=1000, provider_cap=96))
        self.assertEqual(d.desired_concurrency, 96)
        self.assertEqual(d.reason, "queue-pressure")

    def test_backpressure_forces_scale_down(self):
        d = decide(ScaleInput(queued=1000, running=64, completed=100, failed=0,
                              current_concurrency=64, normal_concurrency=16, burst_concurrency=220,
                              backpressure=True))
        self.assertEqual(d.action, "scale_down")
        self.assertLessEqual(d.desired_concurrency, 16)

    def test_failure_rate_forces_scale_down(self):
        d = decide(ScaleInput(queued=1000, running=32, completed=70, failed=30,
                              current_concurrency=32, normal_concurrency=16, burst_concurrency=220))
        self.assertEqual(d.action, "scale_down")
        self.assertEqual(d.reason, "backpressure-or-failure-rate")

    def test_human_gate_only_queue_does_not_scale(self):
        d = decide(ScaleInput(queued=1000, running=0, completed=0, failed=0,
                              current_concurrency=32, normal_concurrency=16, burst_concurrency=220,
                              human_gate_only=True))
        self.assertEqual(d.desired_concurrency, 1)

    def test_idle_scales_to_one(self):
        d = decide(ScaleInput(queued=0, running=0, completed=0, failed=0,
                              current_concurrency=32, normal_concurrency=16, burst_concurrency=220))
        self.assertEqual(d.desired_concurrency, 1)
        self.assertEqual(d.reason, "idle")


if __name__ == "__main__":
    unittest.main()
