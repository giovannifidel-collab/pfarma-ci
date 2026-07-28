import json
import unittest

from razzo.v7.dispatcher_pool import (
    MAX_GENERIC_DISPATCHERS,
    assign_generic_dispatchers,
    dispatcher_matrix_json,
)


def item(n: int) -> dict:
    return {
        "project_id": "p",
        "issue_number": n,
        "collision_domain": f"p/domain-{n}",
        "exact_sha": f"{n:040x}"[-40:],
    }


class DispatcherPoolTests(unittest.TestCase):
    def test_pool_is_generic_and_bounded_to_100(self):
        leases = assign_generic_dispatchers(
            [item(i) for i in range(1, 251)],
            provider_cap=256,
        )
        self.assertEqual(len(leases), MAX_GENERIC_DISPATCHERS)
        self.assertEqual(leases[0].dispatcher_id, "dispatcher-001")
        self.assertEqual(leases[-1].dispatcher_id, "dispatcher-100")
        self.assertEqual(sum(len(lease.work_items) for lease in leases), 250)

    def test_provider_cap_limits_active_dispatchers(self):
        leases = assign_generic_dispatchers(
            [item(i) for i in range(1, 101)],
            provider_cap=32,
        )
        self.assertEqual(len(leases), 32)

    def test_work_count_limits_active_dispatchers(self):
        leases = assign_generic_dispatchers(
            [item(i) for i in range(1, 8)],
            provider_cap=256,
        )
        self.assertEqual(len(leases), 7)
        self.assertTrue(all(len(lease.work_items) == 1 for lease in leases))

    def test_collision_domain_duplicate_is_rejected(self):
        work = [item(1), item(2)]
        work[1]["collision_domain"] = work[0]["collision_domain"]
        with self.assertRaisesRegex(ValueError, "collision domain duplicated"):
            assign_generic_dispatchers(work, provider_cap=32)

    def test_assignment_and_lease_digest_are_deterministic(self):
        work = [item(i) for i in range(1, 13)]
        first = assign_generic_dispatchers(work, provider_cap=4)
        second = assign_generic_dispatchers(work, provider_cap=4)
        self.assertEqual(first, second)
        self.assertEqual([len(x.work_items) for x in first], [3, 3, 3, 3])

    def test_matrix_is_valid_json(self):
        payload = json.loads(dispatcher_matrix_json([item(1), item(2)], provider_cap=2))
        self.assertEqual(len(payload["include"]), 2)
        self.assertEqual(payload["include"][0]["dispatcher_id"], "dispatcher-001")


if __name__ == "__main__":
    unittest.main()
