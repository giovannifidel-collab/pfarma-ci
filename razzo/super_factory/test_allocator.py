import unittest

from razzo.super_factory.allocator import build_snapshot


class SuperFactoryAllocatorTests(unittest.TestCase):
    def test_all_discovered_shards_become_eligible(self):
        snapshot = build_snapshot(
            {"repositories": ["razzo-shard-0001", "razzo-shard-0151"]},
            capacity=1000,
        )
        self.assertEqual(snapshot["eligibleCount"], 2)
        self.assertEqual(snapshot["dormantUnmaterializedCount"], 998)
        self.assertIn("razzo-shard-0001", snapshot["eligible"])
        self.assertIn("razzo-shard-0151", snapshot["eligible"])

    def test_invalid_and_out_of_range_repositories_are_rejected(self):
        snapshot = build_snapshot(
            {
                "repositories": [
                    "razzo-shard-0001",
                    "razzo-shard-1001",
                    "razzo-shard-x001",
                ]
            },
            capacity=1000,
        )
        self.assertEqual(snapshot["eligible"], ["razzo-shard-0001"])
        self.assertEqual(
            snapshot["rejected"],
            ["razzo-shard-1001", "razzo-shard-x001"],
        )

    def test_duplicate_discovery_does_not_duplicate_eligibility(self):
        snapshot = build_snapshot(
            {"repositories": ["razzo-shard-0007", "razzo-shard-0007"]},
            capacity=10,
        )
        self.assertEqual(snapshot["eligibleCount"], 1)
        self.assertEqual(snapshot["dormantUnmaterializedCount"], 9)


if __name__ == "__main__":
    unittest.main()
