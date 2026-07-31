import unittest

from razzo.v7.dispatcher_pool import (
    annotate_work_items,
    assign_dispatchers,
    verify_dispatcher_lease,
)


def item(number: int, *, issue_number: int | None = None) -> dict:
    issue = issue_number if issue_number is not None else number
    return {
        "work_item_id": f"p-issue-{issue}-{number}",
        "fingerprint": f"{number:064x}"[-64:],
        "project_id": "p",
        "issue_number": issue,
        "discovery_source": f"codex-read-only:{issue}:candidate-{number}",
        "collision_domain": f"p/domain-{number}",
        "exact_input_sha": f"{number:040x}"[-40:],
        "actionability_state": "READY",
    }


class DispatcherPoolTests(unittest.TestCase):
    def test_ready_items_receive_distinct_explicit_shards(self):
        leases = assign_dispatchers(
            [item(1), item(2), item(3)],
            provider_cap=3,
            run_id="77",
        )
        self.assertEqual(len(leases), 3)
        self.assertEqual(len({lease.shard_id for lease in leases}), 3)
        self.assertEqual(
            [lease.dispatcher_id for lease in leases],
            ["dispatcher-001", "dispatcher-002", "dispatcher-003"],
        )

    def test_provider_cap_limits_active_shards(self):
        leases = assign_dispatchers(
            [item(1), item(2), item(3)],
            provider_cap=2,
            run_id="77",
        )
        self.assertEqual(len(leases), 2)

    def test_five_product_shards_can_be_allocated(self):
        leases = assign_dispatchers(
            [item(number) for number in range(1, 7)],
            provider_cap=10,
            run_id="77",
        )
        self.assertEqual(len(leases), 5)
        self.assertEqual(len({lease.shard_id for lease in leases}), 5)

    def test_duplicate_collision_domain_is_rejected(self):
        work = [item(1), item(2)]
        work[1]["collision_domain"] = work[0]["collision_domain"]
        with self.assertRaisesRegex(ValueError, "collision domain duplicated"):
            assign_dispatchers(work, provider_cap=2, run_id="77")

    def test_duplicate_fingerprint_is_rejected(self):
        work = [item(1), item(2)]
        work[1]["fingerprint"] = work[0]["fingerprint"]
        with self.assertRaisesRegex(ValueError, "fingerprint duplicated"):
            assign_dispatchers(work, provider_cap=2, run_id="77")

    def test_duplicate_materialized_source_is_rejected(self):
        work = [item(1), item(2)]
        work[1]["issue_number"] = work[0]["issue_number"]
        work[1]["discovery_source"] = work[0]["discovery_source"]
        with self.assertRaisesRegex(ValueError, "materialized source duplicated"):
            assign_dispatchers(work, provider_cap=2, run_id="77")

    def test_distinct_contracts_from_same_umbrella_issue_are_allowed(self):
        leases = assign_dispatchers(
            [item(1, issue_number=99), item(2, issue_number=99)],
            provider_cap=2,
            run_id="77",
        )
        self.assertEqual(len(leases), 2)

    def test_non_ready_item_never_reaches_dispatch(self):
        work = [item(1)]
        work[0]["actionability_state"] = "NOT_ACTIONABLE"
        with self.assertRaisesRegex(ValueError, "non-READY"):
            assign_dispatchers(work, provider_cap=1, run_id="77")

    def test_lease_digest_is_bound_to_run_and_shard(self):
        lease = assign_dispatchers([item(1)], provider_cap=1, run_id="77")[0]
        verify_dispatcher_lease(
            lease.dispatcher_id,
            [lease.enveloped_item()],
            lease.lease_digest,
            lease.shard_id,
            "77",
        )
        with self.assertRaisesRegex(ValueError, "lease digest mismatch"):
            verify_dispatcher_lease(
                lease.dispatcher_id,
                [lease.enveloped_item()],
                lease.lease_digest,
                lease.shard_id,
                "78",
            )

    def test_worker_matrix_contains_same_verified_envelope(self):
        workers, leases = annotate_work_items(
            [item(1), item(2)],
            provider_cap=2,
            run_id="77",
        )
        self.assertEqual(len(workers), 2)
        self.assertEqual(len(leases), 2)
        self.assertEqual(workers[0]["shard_id"], leases[0].shard_id)
        self.assertEqual(workers[0]["lease_digest"], leases[0].lease_digest)


if __name__ == "__main__":
    unittest.main()
