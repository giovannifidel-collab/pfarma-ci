from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from razzo.kernel.observability import (
    CapabilityState,
    CellHeartbeat,
    CellState,
    FactoryState,
    FactoryStatus,
    FactoryStatusStore,
    ProductReceipt,
    StatusConflict,
)

BASE_SHA = "b" * 40
CANDIDATE_SHA = "c" * 40
CONTROL_SHA = "a" * 40


def receipt() -> ProductReceipt:
    return ProductReceipt(
        repository="giovannifidel-collab/project-giovanni",
        pull_request=964,
        capability_fingerprint="project-giovanni:progress-profile-snapshot:v1",
        base_branch="integration/razzo",
        base_sha=BASE_SHA,
        candidate_sha=CANDIDATE_SHA,
        changed_files=("lib/progressProfileSnapshot.ts", "factory/progress-profile-snapshot.test.mjs"),
        product_ci_name="RAZZO Progress Profile Product CI exact-head",
        product_ci_run_id=30827588438,
        product_ci_sha=CANDIDATE_SHA,
        product_ci_conclusion="success",
        robot_qa_name="RAZZO Progress Profile Robot Collaudatore exact-head",
        robot_qa_run_id=30827586905,
        robot_qa_sha=CANDIDATE_SHA,
        robot_qa_conclusion="success",
        state=CapabilityState.READY_FOR_HUMAN_REVIEW,
    )


def status() -> FactoryStatus:
    return FactoryStatus(
        schema_version=1,
        generation=0,
        updated_at="2026-08-03T15:45:00Z",
        factory_state=FactoryState.RUNNING,
        mode="PILOT",
        control_plane_sha=CONTROL_SHA,
        enabled_cells=("RAZZO-Cell-00",),
        max_active_capabilities=1,
        max_shreds=2,
        active_capability="project-giovanni:progress-profile-snapshot:v1",
        capability_state=CapabilityState.READY_FOR_HUMAN_REVIEW,
        last_heartbeat=CellHeartbeat(
            cell_id="RAZZO-Cell-00",
            observed_at="2026-08-03T15:45:00Z",
            schedule_minute=0,
            state=CellState.SCHEDULED,
            control_plane_sha=CONTROL_SHA,
            message="Factory activation retained one protected cell.",
        ),
        product_receipt=receipt(),
        live_log_issue=753,
    )


class ObservabilityTests(unittest.TestCase):
    def test_round_trip_and_markdown(self) -> None:
        original = status()
        encoded = original.to_dict()
        decoded = FactoryStatus.from_dict(json.loads(json.dumps(encoded)))
        self.assertEqual(decoded, original)
        markdown = decoded.render_markdown()
        self.assertIn("project-giovanni#964", markdown)
        self.assertIn(CANDIDATE_SHA, markdown)
        self.assertIn("Product CI", markdown)
        self.assertIn("Robot QA", markdown)

    def test_exact_head_mismatch_fails_closed(self) -> None:
        broken = replace(receipt(), robot_qa_sha="d" * 40)
        with self.assertRaisesRegex(ValueError, "one exact SHA"):
            broken.validate()

    def test_empty_diff_fails_closed(self) -> None:
        broken = replace(receipt(), changed_files=())
        with self.assertRaisesRegex(ValueError, "changed files"):
            broken.validate()

    def test_one_cell_pilot_limit(self) -> None:
        broken = replace(status(), enabled_cells=("RAZZO-Cell-00", "RAZZO-Cell-12"))
        with self.assertRaisesRegex(ValueError, "one enabled cell"):
            broken.validate()

    def test_running_heartbeat_requires_run_id(self) -> None:
        heartbeat = replace(status().last_heartbeat, state=CellState.RUNNING, run_id=None)
        with self.assertRaisesRegex(ValueError, "requires run_id"):
            heartbeat.validate()

    def test_active_capability_requires_receipt(self) -> None:
        broken = replace(status(), product_receipt=None)
        with self.assertRaisesRegex(ValueError, "requires product receipt"):
            broken.validate()

    def test_atomic_compare_and_swap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = FactoryStatusStore(Path(directory) / "factory-status.json")
            initial = status()
            store.compare_and_swap(-1, initial)
            self.assertEqual(store.load(), initial)
            next_status = replace(initial, generation=1, updated_at="2026-08-03T16:00:00Z")
            store.compare_and_swap(0, next_status)
            self.assertEqual(store.load(), next_status)
            with self.assertRaises(StatusConflict):
                store.compare_and_swap(0, replace(next_status, generation=1))

    def test_repository_status_fixture_is_valid(self) -> None:
        fixture = Path(__file__).resolve().parents[1] / "state" / "factory-status.json"
        parsed = FactoryStatus.from_dict(json.loads(fixture.read_text(encoding="utf-8")))
        self.assertEqual(parsed.schema_version, 1)
        self.assertEqual(parsed.max_active_capabilities, 1)
        self.assertLessEqual(parsed.max_shreds, 2)
        self.assertEqual(parsed.live_log_issue, 753)


if __name__ == "__main__":
    unittest.main()
