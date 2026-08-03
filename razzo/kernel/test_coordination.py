from __future__ import annotations

import json
import random
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from razzo.kernel.coordination import (
    GlobalLease,
    GlobalLeaseStore,
    LeaseConflict,
    LeaseHeld,
    LeaseState,
    simulate_trigger_race,
)

CONTROL_SHA = "f" * 40
NOW = datetime(2026, 8, 3, 20, 23, tzinfo=timezone.utc)


def free_lease() -> GlobalLease:
    return GlobalLease(
        schema_version=1,
        generation=0,
        state=LeaseState.FREE,
        updated_at="2026-08-03T20:23:00Z",
        control_plane_sha=CONTROL_SHA,
        terminal_reason="OWNER_PAUSED",
    )


class CoordinationTests(unittest.TestCase):
    def test_five_trigger_race_has_one_winner(self) -> None:
        contenders = tuple(f"run-{index}" for index in range(5))
        for seed in range(100):
            order = list(range(5))
            random.Random(seed).shuffle(order)
            result = simulate_trigger_race(
                free_lease(),
                contenders=contenders,
                attempt_order=order,
                now=NOW,
            )
            self.assertEqual(result.winner, contenders[order[0]])
            self.assertEqual(len(result.blocked_runs), 4)
            self.assertEqual(result.final_generation, 1)

    def test_same_owner_acquire_is_idempotent(self) -> None:
        lease = free_lease().acquire(
            run_id="run-a", now=NOW, ttl_seconds=900, control_plane_sha=CONTROL_SHA
        )
        self.assertIs(lease.acquire(
            run_id="run-a", now=NOW, ttl_seconds=900, control_plane_sha=CONTROL_SHA
        ), lease)

    def test_other_owner_is_blocked(self) -> None:
        lease = free_lease().acquire(
            run_id="run-a", now=NOW, ttl_seconds=900, control_plane_sha=CONTROL_SHA
        )
        with self.assertRaises(LeaseHeld):
            lease.acquire(
                run_id="run-b", now=NOW, ttl_seconds=900, control_plane_sha=CONTROL_SHA
            )

    def test_expired_lease_is_recoverable(self) -> None:
        first = free_lease().acquire(
            run_id="run-a", now=NOW, ttl_seconds=60, control_plane_sha=CONTROL_SHA
        )
        second = first.acquire(
            run_id="run-b",
            now=NOW + timedelta(seconds=61),
            ttl_seconds=900,
            control_plane_sha=CONTROL_SHA,
        )
        self.assertEqual(second.owner_run_id, "run-b")
        self.assertEqual(second.generation, 2)

    def test_bind_and_release(self) -> None:
        acquired = free_lease().acquire(
            run_id="run-a", now=NOW, ttl_seconds=900, control_plane_sha=CONTROL_SHA
        )
        bound = acquired.bind_capability(
            run_id="run-a",
            now=NOW + timedelta(seconds=1),
            capability_fingerprint="project-giovanni:proof:v1",
            repository="giovannifidel-collab/project-giovanni",
            pull_request=999,
        )
        self.assertEqual(bound.canonical_pr, 999)
        self.assertIs(bound.bind_capability(
            run_id="run-a",
            now=NOW + timedelta(seconds=2),
            capability_fingerprint="project-giovanni:proof:v1",
            repository="giovannifidel-collab/project-giovanni",
            pull_request=999,
        ), bound)
        released = bound.release(
            run_id="run-a", now=NOW + timedelta(seconds=3), reason="SIMULATION_COMPLETE"
        )
        self.assertEqual(released.state, LeaseState.FREE)
        self.assertIsNone(released.owner_run_id)

    def test_atomic_compare_and_swap_rejects_stale_writer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "global-lease.json"
            path.write_text(json.dumps(free_lease().to_dict()), encoding="utf-8")
            store = GlobalLeaseStore(path)
            a = store.load().acquire(
                run_id="run-a", now=NOW, ttl_seconds=900, control_plane_sha=CONTROL_SHA
            )
            b = store.load().acquire(
                run_id="run-b", now=NOW, ttl_seconds=900, control_plane_sha=CONTROL_SHA
            )
            store.compare_and_swap(expected_generation=0, lease=a)
            with self.assertRaises(LeaseConflict):
                store.compare_and_swap(expected_generation=0, lease=b)

    def test_partial_capability_binding_fails_closed(self) -> None:
        broken = GlobalLease(
            schema_version=1,
            generation=1,
            state=LeaseState.HELD,
            updated_at="2026-08-03T20:23:00Z",
            control_plane_sha=CONTROL_SHA,
            owner_run_id="run-a",
            acquired_at="2026-08-03T20:23:00Z",
            expires_at="2026-08-03T20:38:00Z",
            capability_fingerprint="project:test:v1",
        )
        with self.assertRaisesRegex(ValueError, "complete or absent"):
            broken.validate()


if __name__ == "__main__":
    unittest.main()
