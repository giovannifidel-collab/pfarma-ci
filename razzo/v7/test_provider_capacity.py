import unittest

from razzo.v7.provider_capacity import (
    ProviderObservation,
    derive_operational_cap,
    median_queue_wait,
    observed_peak,
)


class ProviderCapacityTests(unittest.TestCase):
    def test_grows_only_on_measured_throughput_gain(self):
        decision = derive_operational_cap(
            ProviderObservation(
                observed_peak=120,
                queue_wait_seconds=20,
                throughput_per_minute=48,
                prior_throughput_per_minute=40,
            ),
            normal_concurrency=64,
            registry_burst=1000,
            previous_cap=220,
        )
        self.assertEqual(decision.action, "scale_up")
        self.assertEqual(decision.operational_cap, 330)

    def test_high_queue_wait_scales_down(self):
        decision = derive_operational_cap(
            ProviderObservation(
                observed_peak=90,
                queue_wait_seconds=180,
                throughput_per_minute=42,
                prior_throughput_per_minute=40,
                queued_runs=12,
                in_progress_runs=3,
            ),
            normal_concurrency=64,
            registry_burst=1000,
            previous_cap=220,
        )
        self.assertEqual(decision.action, "scale_down")
        self.assertEqual(decision.reason, "provider-queue-pressure")
        self.assertEqual(decision.operational_cap, 90)

    def test_throughput_regression_scales_down(self):
        decision = derive_operational_cap(
            ProviderObservation(
                observed_peak=150,
                queue_wait_seconds=30,
                throughput_per_minute=30,
                prior_throughput_per_minute=40,
            ),
            normal_concurrency=64,
            registry_burst=1000,
            previous_cap=220,
        )
        self.assertEqual(decision.action, "scale_down")
        self.assertEqual(decision.operational_cap, 150)

    def test_never_exceeds_registry_burst(self):
        decision = derive_operational_cap(
            ProviderObservation(
                observed_peak=900,
                queue_wait_seconds=5,
                throughput_per_minute=120,
                prior_throughput_per_minute=80,
            ),
            normal_concurrency=64,
            registry_burst=1000,
            previous_cap=900,
        )
        self.assertEqual(decision.operational_cap, 1000)

    def test_overlap_peak_is_measured(self):
        self.assertEqual(observed_peak([(0, 10), (1, 9), (2, 3), (10, 20)]), 3)

    def test_median_queue_wait(self):
        self.assertEqual(median_queue_wait([10, 30, 20]), 20.0)


if __name__ == "__main__":
    unittest.main()
