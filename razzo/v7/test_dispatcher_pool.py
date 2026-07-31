import json
import unittest

from razzo.v7.dispatcher_pool import assign_generic_dispatchers, dispatcher_matrix_json, verify_dispatcher_lease


def item(n: int) -> dict:
    return {
        "work_item_id": f"p-issue-{n}",
        "fingerprint": f"{n:064x}"[-64:],
        "project_id": "p",
        "issue_number": n,
        "collision_domain": f"p/domain-{n}",
        "exact_input_sha": f"{n:040x}"[-40:],
        "actionability_state": "READY",
    }


class DispatcherPoolTests(unittest.TestCase):
    def test_one_ready_item_gets_one_explicit_shard(self):
        leases = assign_generic_dispatchers([item(1), item(2), item(3)], provider_cap=10, run_id="77")
        self.assertEqual(len(leases), 3)
        self.assertEqual(len({x.shard_id for x in leases}), 3)
        self.assertTrue(all(x.shard_id.startswith("razzo-shard-") for x in leases))
        self.assertEqual([x.dispatcher_id for x in leases], ["dispatcher-001", "dispatcher-002", "dispatcher-003"])

    def test_provider_cap_limits_active_shards(self):
        leases = assign_generic_dispatchers([item(1), item(2), item(3)], provider_cap=2, run_id="77")
        self.assertEqual(len(leases), 2)

    def test_duplicate_collision_domain_is_rejected(self):
        work = [item(1), item(2)]
        work[1]["collision_domain"] = work[0]["collision_domain"]
        with self.assertRaisesRegex(ValueError, "collision domain duplicated"):
            assign_generic_dispatchers(work, provider_cap=2)

    def test_duplicate_fingerprint_is_rejected(self):
        work = [item(1), item(2)]
        work[1]["fingerprint"] = work[0]["fingerprint"]
        with self.assertRaisesRegex(ValueError, "fingerprint duplicated"):
            assign_generic_dispatchers(work, provider_cap=2)

    def test_same_issue_is_not_replicated(self):
        work = [item(1), item(2)]
        work[1]["issue_number"] = work[0]["issue_number"]
        with self.assertRaisesRegex(ValueError, "same issue duplicated"):
            assign_generic_dispatchers(work, provider_cap=2)

    def test_non_ready_item_never_reaches_product_matrix(self):
        work = [item(1)]
        work[0]["actionability_state"] = "NOT_ACTIONABLE"
        with self.assertRaisesRegex(ValueError, "non-READY"):
            assign_generic_dispatchers(work, provider_cap=1)

    def test_lease_digest_is_verifiable_and_run_bound(self):
        lease = assign_generic_dispatchers([item(1)], provider_cap=1, run_id="77")[0]
        enveloped = lease.enveloped_item()
        verify_dispatcher_lease(lease.dispatcher_id, [enveloped], lease.lease_digest, lease.shard_id, "77")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            verify_dispatcher_lease(lease.dispatcher_id, [enveloped], lease.lease_digest, lease.shard_id, "78")

    def test_matrix_exposes_shard_and_single_work_item(self):
        payload = json.loads(dispatcher_matrix_json([item(1), item(2)], provider_cap=2, run_id="77"))
        self.assertEqual(len(payload["include"]), 2)
        self.assertEqual(payload["include"][0]["shard_id"], "razzo-shard-0002")
        self.assertEqual(payload["include"][0]["work_count"], 1)


if __name__ == "__main__":
    unittest.main()
