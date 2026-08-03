from __future__ import annotations

import unittest

from .runtime import ActivationPolicy, ExecutionMode, NodeState, RuntimeEvent, RuntimeJournal, WaveState
from .testing import make_plan


class PolicyTests(unittest.TestCase):
    def test_shadow_forbids_writes(self):
        with self.assertRaisesRegex(ValueError, "shadow"):
            ActivationPolicy(ExecutionMode.SHADOW, False, product_writes_allowed=True).validate()

    def test_sandbox_requires_fixture_only(self):
        with self.assertRaisesRegex(ValueError, "fixture-only"):
            ActivationPolicy(ExecutionMode.SANDBOX, False).validate()

    def test_pilot_forbids_auto_merge(self):
        with self.assertRaisesRegex(ValueError, "cannot auto-merge"):
            ActivationPolicy(ExecutionMode.PILOT, False, merge_allowed=True).validate()

    def test_production_requires_provider(self):
        with self.assertRaisesRegex(ValueError, "eligible"):
            ActivationPolicy(ExecutionMode.PRODUCTION, False, human_gate_approved=True, product_writes_allowed=True).validate()

    def test_production_requires_human_gate(self):
        with self.assertRaisesRegex(ValueError, "human"):
            ActivationPolicy(ExecutionMode.PRODUCTION, True, product_writes_allowed=True).validate()


def make_journal(mode=ExecutionMode.SANDBOX):
    plan = make_plan()
    wave = plan.next_wave(max_workers=2)
    policy = ActivationPolicy(mode, False, fixture_only=(mode is ExecutionMode.SANDBOX))
    return plan, wave, RuntimeJournal(plan.capability_id, plan.revision_id, wave.wave_id, wave.exact_base_sha, wave.node_ids, policy)


def ev(plan, wave, kind, node_id=None, collision_domain=None, **payload):
    return RuntimeEvent(kind, plan.capability_id, plan.revision_id, wave.wave_id, wave.exact_base_sha, node_id, collision_domain, tuple(sorted(payload.items())))


class JournalTests(unittest.TestCase):
    def test_duplicate_event_is_idempotent(self):
        plan, wave, journal = make_journal()
        event = ev(plan, wave, "WAVE_STARTED")
        self.assertTrue(journal.apply(event))
        self.assertFalse(journal.apply(event))

    def test_event_scope_mismatch_fails(self):
        plan, wave, journal = make_journal()
        bad = RuntimeEvent("WAVE_STARTED", "f" * 64, plan.revision_id, wave.wave_id, wave.exact_base_sha)
        with self.assertRaisesRegex(ValueError, "scope"):
            journal.apply(bad)

    def test_collision_lease_is_rejected(self):
        plan, wave, journal = make_journal()
        journal.apply(ev(plan, wave, "WAVE_STARTED"))
        journal.apply(ev(plan, wave, "NODE_LEASED", wave.node_ids[0], "same"))
        with self.assertRaisesRegex(ValueError, "collision"):
            journal.apply(ev(plan, wave, "NODE_LEASED", wave.node_ids[1], "same"))

    def test_success_releases_lease(self):
        plan, wave, journal = make_journal()
        journal.apply(ev(plan, wave, "WAVE_STARTED"))
        node = wave.node_ids[0]
        journal.apply(ev(plan, wave, "NODE_LEASED", node, "d1"))
        journal.apply(ev(plan, wave, "NODE_SUCCEEDED", node))
        self.assertNotIn(node, journal.active_leases)
        self.assertIs(journal.node_states[node], NodeState.SUCCEEDED)

    def test_failure_moves_to_replan(self):
        plan, wave, journal = make_journal()
        journal.apply(ev(plan, wave, "WAVE_STARTED"))
        node = wave.node_ids[0]
        journal.apply(ev(plan, wave, "NODE_LEASED", node, "d1"))
        journal.apply(ev(plan, wave, "NODE_FAILED", node))
        self.assertIs(journal.wave_state, WaveState.NEEDS_REPLAN)

    def test_assembly_requires_every_node(self):
        plan, wave, journal = make_journal()
        journal.apply(ev(plan, wave, "WAVE_STARTED"))
        with self.assertRaisesRegex(ValueError, "every node"):
            journal.apply(ev(plan, wave, "ASSEMBLY_STARTED"))

    def test_exact_head_gate_rejects_stale_ci(self):
        plan, wave, journal = make_journal()
        journal.apply(ev(plan, wave, "WAVE_STARTED"))
        for index, node in enumerate(wave.node_ids):
            journal.apply(ev(plan, wave, "NODE_LEASED", node, f"d{index}"))
            journal.apply(ev(plan, wave, "NODE_SUCCEEDED", node))
        journal.apply(ev(plan, wave, "ASSEMBLY_STARTED"))
        journal.apply(ev(plan, wave, "CANDIDATE_CREATED", candidate_sha="b" * 40))
        with self.assertRaisesRegex(ValueError, "exact SHA"):
            journal.apply(ev(plan, wave, "PRODUCT_CI_PASSED", tested_sha="c" * 40))

    def test_merge_is_blocked_in_sandbox(self):
        plan, wave, journal = make_journal()
        journal.apply(ev(plan, wave, "WAVE_STARTED"))
        for index, node in enumerate(wave.node_ids):
            journal.apply(ev(plan, wave, "NODE_LEASED", node, f"d{index}"))
            journal.apply(ev(plan, wave, "NODE_SUCCEEDED", node))
        sha = "b" * 40
        journal.apply(ev(plan, wave, "ASSEMBLY_STARTED"))
        journal.apply(ev(plan, wave, "CANDIDATE_CREATED", candidate_sha=sha))
        journal.apply(ev(plan, wave, "PRODUCT_CI_PASSED", tested_sha=sha))
        journal.apply(ev(plan, wave, "ROBOT_QA_PASSED", tested_sha=sha))
        journal.apply(ev(plan, wave, "MERGE_READY"))
        with self.assertRaisesRegex(ValueError, "forbids merge"):
            journal.apply(ev(plan, wave, "MERGED", merged_sha="d" * 40))

    def test_replay_reproduces_snapshot(self):
        plan, wave, journal = make_journal()
        events = [ev(plan, wave, "WAVE_STARTED")]
        journal.apply(events[0])
        replayed = RuntimeJournal.replay(capability_id=plan.capability_id, revision_id=plan.revision_id, wave_id=wave.wave_id, exact_sha=wave.exact_base_sha, node_ids=wave.node_ids, policy=journal.policy, events=events)
        self.assertEqual(journal.snapshot(), replayed.snapshot())


if __name__ == "__main__":
    unittest.main()
