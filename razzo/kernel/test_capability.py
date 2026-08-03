from __future__ import annotations

import unittest
from dataclasses import replace

from .capability import CapabilityNode, HomoLevel, compile_capability, normalize_surface, surfaces_overlap
from .testing import A1, A2, make_nodes, make_plan, make_spec


class SurfaceSecurityTests(unittest.TestCase):
    def test_accepts_repository_relative_path(self):
        self.assertEqual(normalize_surface("src/module.py"), "src/module.py")

    def test_rejects_absolute_path(self):
        with self.assertRaisesRegex(ValueError, "repository-relative"):
            normalize_surface("/etc/passwd")

    def test_rejects_parent_traversal(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            normalize_surface("safe/../secret.py")

    def test_rejects_dot_segment(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            normalize_surface("safe/./file.py")

    def test_rejects_windows_separator(self):
        with self.assertRaisesRegex(ValueError, "POSIX"):
            normalize_surface("safe\\file.py")

    def test_rejects_glob_in_parent_segment(self):
        with self.assertRaisesRegex(ValueError, "final"):
            normalize_surface("src*/file.py")

    def test_detects_prefix_overlap(self):
        self.assertTrue(surfaces_overlap("src/a.py", "src"))

    def test_distinct_roots_do_not_overlap(self):
        self.assertFalse(surfaces_overlap("backend/a.py", "frontend/a.py"))


class CapabilityIdentityTests(unittest.TestCase):
    def test_capability_identity_is_stable_across_base_sha(self):
        first = make_spec(sha="a" * 40)
        second = make_spec(sha="b" * 40)
        self.assertEqual(first.capability_id, second.capability_id)

    def test_revision_changes_with_base_sha(self):
        self.assertNotEqual(make_plan(sha="a" * 40).revision_id, make_plan(sha="b" * 40).revision_id)

    def test_revision_is_deterministic(self):
        self.assertEqual(make_plan().revision_id, make_plan().revision_id)

    def test_wave_id_ignores_display_index(self):
        plan = make_plan()
        one = plan.next_wave(display_index=1)
        two = plan.next_wave(display_index=99)
        self.assertIsNotNone(one)
        self.assertIsNotNone(two)
        self.assertEqual(one.wave_id, two.wave_id)


class CapabilityValidationTests(unittest.TestCase):
    def test_topological_order(self):
        self.assertEqual(make_plan().topological_order(), ("N001", "N002", "N003", "N004", "N005"))

    def test_rejects_cycle(self):
        nodes = list(make_nodes())
        nodes[0] = replace(nodes[0], dependencies=("N005",))
        with self.assertRaisesRegex(ValueError, "cycle"):
            compile_capability(make_spec(), nodes)

    def test_rejects_unknown_dependency(self):
        nodes = list(make_nodes())
        nodes[1] = replace(nodes[1], dependencies=("N999",))
        with self.assertRaisesRegex(ValueError, "unknown dependencies"):
            compile_capability(make_spec(), nodes)

    def test_rejects_uncovered_acceptance(self):
        nodes = tuple(replace(node, acceptance_subset=tuple(item for item in node.acceptance_subset if item != A2) or (A1,)) for node in make_nodes())
        with self.assertRaisesRegex(ValueError, "not fully covered"):
            compile_capability(make_spec(), nodes)

    def test_rejects_foreign_acceptance(self):
        nodes = list(make_nodes())
        nodes[0] = replace(nodes[0], acceptance_subset=("foreign",))
        with self.assertRaisesRegex(ValueError, "unknown acceptance"):
            compile_capability(make_spec(), nodes)

    def test_rejects_independent_surface_overlap(self):
        nodes = list(make_nodes())
        nodes[3] = replace(nodes[3], dependencies=(), allowed_surfaces=("inventory/models",))
        with self.assertRaisesRegex(ValueError, "overlapping"):
            compile_capability(make_spec(), nodes)

    def test_rejects_independent_collision_domain_overlap(self):
        nodes = list(make_nodes())
        nodes[3] = replace(nodes[3], dependencies=(), collision_domain="inventory/schema")
        with self.assertRaisesRegex(ValueError, "share a collision domain"):
            compile_capability(make_spec(), nodes)

    def test_allows_serial_collision_domain_reuse(self):
        nodes = list(make_nodes())
        nodes[1] = replace(nodes[1], collision_domain="inventory/schema")
        plan = compile_capability(make_spec(), nodes)
        self.assertEqual(plan.nodes[1].collision_domain, "inventory/schema")

    def test_completion_requires_dependency_closure(self):
        with self.assertRaisesRegex(ValueError, "dependency-closed"):
            make_plan().completion_ratio(("N002",))

    def test_completion_is_cost_weighted(self):
        self.assertAlmostEqual(make_plan().completion_ratio(("N001", "N002")), 4 / 8)


class WaveTests(unittest.TestCase):
    def test_materializes_dependency_ordered_wave(self):
        wave = make_plan().next_wave(max_workers=5)
        self.assertEqual(wave.node_ids, ("N001", "N002", "N004", "N003", "N005"))

    def test_bounded_worker_limit(self):
        wave = make_plan().next_wave(max_workers=2)
        self.assertEqual(len(wave.node_ids), 2)

    def test_rejects_worker_limit_above_kernel_cap(self):
        with self.assertRaisesRegex(ValueError, "1..5"):
            make_plan().next_wave(max_workers=6)

    def test_tampered_wave_node_is_rejected(self):
        plan = make_plan()
        wave = plan.next_wave()
        tampered = replace(wave, node_ids=("N999",))
        with self.assertRaisesRegex(ValueError, "outside the plan"):
            plan.validate_wave(tampered)

    def test_tampered_revision_is_rejected(self):
        plan = make_plan()
        wave = plan.next_wave()
        with self.assertRaisesRegex(ValueError, "revision"):
            plan.validate_wave(replace(wave, revision_id="f" * 64))

    def test_stale_sha_requires_new_plan_revision(self):
        plan = make_plan()
        wave = plan.next_wave()
        with self.assertRaisesRegex(ValueError, "exact SHA"):
            plan.validate_wave(replace(wave, exact_base_sha="b" * 40))

    def test_payload_preserves_verification(self):
        plan = make_plan()
        wave = plan.next_wave()
        payload = plan.to_controller_payload(wave)
        expected = {node.node_id: list(node.verification) for node in plan.validate_wave(wave)}
        self.assertEqual(payload["metadata"]["verification_by_node"], expected)

    def test_retry_payload_identity_is_stable(self):
        plan = make_plan()
        first = plan.to_controller_payload(plan.next_wave(display_index=1))
        second = plan.to_controller_payload(plan.next_wave(display_index=2))
        self.assertEqual(first["goal"], second["goal"])
        self.assertEqual(first["metadata"]["wave_id"], second["metadata"]["wave_id"])

    def test_active_collision_domain_blocks_wave(self):
        plan = make_plan()
        wave = plan.next_wave(active_collision_domains=("inventory/schema",))
        self.assertIsNone(wave)


class ScoreTests(unittest.TestCase):
    def test_weighted_score_accounts_for_risk_and_cost(self):
        low_risk = CapabilityNode("N010", "a", HomoLevel.CELL, "a", (), ("a.py",), (A1,), "inventory/schema", ("test",), priority=50, product_value=50, risk=0, estimated_cost=1)
        high_risk = replace(low_risk, node_id="N011", risk=100, estimated_cost=100)
        self.assertGreater(low_risk.weighted_score, high_risk.weighted_score)


if __name__ == "__main__":
    unittest.main()
