from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .capability import CapabilityNode, CapabilitySpec, HomoLevel, compile_capability
from .canonical import ProjectContract, assert_verification_preserved, build_canonical_objective
from .runtime import ActivationPolicy, ExecutionMode
from .shadow import analyze_shadow
from .simulator import FaultProfile, run_campaign

_SHA = "a" * 40
_A1 = "The fixture operator can list expiring batches by date."
_A2 = "The fixture operator can export the filtered result."
_A3 = "Invalid fixture expiry dates are rejected with a useful error."


@dataclass(frozen=True)
class ProtectedPilotReport:
    mode: str
    fixture_only: bool
    product_writes_allowed: bool
    merge_allowed: bool
    capability_id: str
    revision_id: str
    wave_id: str
    objective_fingerprint: str
    objective_branch: str
    shred_count: int
    shadow_mutations: int
    simulation_runs: int
    simulation_successes: int
    simulation_failures: int
    stale_evidence_rejected: int
    duplicate_events_ignored: int
    invariant_failure_examples: tuple[str, ...]
    activation_status: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def fixture_plan():
    spec = CapabilitySpec(
        project_id="razzo-sandbox-fixture",
        title="Protected inventory expiry fixture",
        user_outcome="Validate the pre-launch factory without touching a product repository.",
        exact_base_sha=_SHA,
        acceptance_criteria=(_A1, _A2, _A3),
        collision_domains=(
            "fixture/schema",
            "fixture/query",
            "fixture/export",
            "fixture/ui",
            "fixture/qa",
        ),
    )
    nodes = (
        CapabilityNode(
            node_id="N001",
            title="Fixture schema",
            level=HomoLevel.CELL,
            responsibility="Create the deterministic fixture expiry schema contract.",
            dependencies=(),
            allowed_surfaces=("razzo/kernel/fixtures/schema.py",),
            acceptance_subset=(_A3,),
            collision_domain="fixture/schema",
            verification=("python -m unittest razzo.kernel.test_capability",),
            priority=100,
            product_value=80,
            unlock_value=100,
            parallel_value=70,
            risk=10,
            estimated_cost=2,
        ),
        CapabilityNode(
            node_id="N002",
            title="Fixture query",
            level=HomoLevel.CELL,
            responsibility="Implement the deterministic fixture expiry query contract.",
            dependencies=("N001",),
            allowed_surfaces=("razzo/kernel/fixtures/query.py",),
            acceptance_subset=(_A1,),
            collision_domain="fixture/query",
            verification=("python -m unittest razzo.kernel.test_canonical",),
            priority=95,
            product_value=100,
            unlock_value=90,
            parallel_value=80,
            risk=10,
            estimated_cost=2,
        ),
        CapabilityNode(
            node_id="N003",
            title="Fixture export",
            level=HomoLevel.CELL,
            responsibility="Implement deterministic export evidence for the fixture.",
            dependencies=("N002",),
            allowed_surfaces=("razzo/kernel/fixtures/export.py",),
            acceptance_subset=(_A2,),
            collision_domain="fixture/export",
            verification=("python -m unittest razzo.kernel.test_runtime",),
            priority=80,
            product_value=90,
            unlock_value=40,
            parallel_value=90,
            risk=10,
            estimated_cost=1,
        ),
        CapabilityNode(
            node_id="N004",
            title="Fixture interface",
            level=HomoLevel.ORGAN,
            responsibility="Expose the fixture query and export journey contract.",
            dependencies=("N002",),
            allowed_surfaces=("razzo/kernel/fixtures/interface.py",),
            acceptance_subset=(_A1, _A2),
            collision_domain="fixture/ui",
            verification=("python -m unittest razzo.kernel.test_shadow",),
            priority=90,
            product_value=100,
            unlock_value=50,
            parallel_value=100,
            risk=15,
            estimated_cost=2,
        ),
        CapabilityNode(
            node_id="N005",
            title="Fixture journey QA",
            level=HomoLevel.SYSTEM,
            responsibility="Verify the complete fixture journey and exact-head invariants.",
            dependencies=("N003", "N004"),
            allowed_surfaces=("razzo/kernel/fixtures/journey.py",),
            acceptance_subset=(_A1, _A2, _A3),
            collision_domain="fixture/qa",
            verification=("python -m unittest razzo.kernel.test_pilot",),
            priority=85,
            product_value=100,
            unlock_value=20,
            parallel_value=20,
            risk=5,
            estimated_cost=1,
        ),
    )
    return compile_capability(spec, nodes)


def run_protected_pilot(*, simulation_runs: int = 1000) -> ProtectedPilotReport:
    if simulation_runs < 1:
        raise ValueError("simulation_runs must be positive")
    policy = ActivationPolicy(
        mode=ExecutionMode.PILOT,
        provider_eligible=False,
        human_gate_approved=False,
        product_writes_allowed=False,
        merge_allowed=False,
        fixture_only=True,
    )
    policy.validate()
    plan = fixture_plan()
    project = ProjectContract(
        project_id=plan.spec.project_id,
        repository="giovannifidel-collab/pfarma-ci",
        integration_lane="agent/razzo-factory-prelaunch",
        max_builders=5,
    )
    shadow = analyze_shadow(plan, project=project, max_workers=5)
    if shadow.next_wave_id is None:
        raise RuntimeError("protected pilot could not materialize a wave")
    wave = plan.next_wave(max_workers=5)
    assert wave is not None
    objective = build_canonical_objective(plan, wave, project)
    expected_verification = [command for node in plan.validate_wave(wave) for command in node.verification]
    assert_verification_preserved(objective, expected_verification)
    campaign = run_campaign(
        plan,
        seeds=range(simulation_runs),
        fault_profile=FaultProfile(
            node_failure_rate=0.04,
            duplicate_event_rate=0.10,
            stale_ci_rate=0.03,
            stale_qa_rate=0.03,
            crash_replay_rate=0.12,
        ),
        max_workers=5,
    )
    activation_status = (
        "PRELAUNCH_GATES_GREEN"
        if campaign.failures == 0 and not campaign.invariant_failure_examples
        else "PRELAUNCH_GATES_FAILED"
    )
    return ProtectedPilotReport(
        mode=policy.mode.value,
        fixture_only=policy.fixture_only,
        product_writes_allowed=policy.product_writes_allowed,
        merge_allowed=policy.merge_allowed,
        capability_id=plan.capability_id,
        revision_id=plan.revision_id,
        wave_id=wave.wave_id,
        objective_fingerprint=objective.fingerprint,
        objective_branch=objective.branch,
        shred_count=len(objective.shreds),
        shadow_mutations=shadow.mutations_performed,
        simulation_runs=campaign.runs,
        simulation_successes=campaign.successes,
        simulation_failures=campaign.failures,
        stale_evidence_rejected=campaign.total_stale_rejections,
        duplicate_events_ignored=campaign.total_duplicate_ignores,
        invariant_failure_examples=campaign.invariant_failure_examples,
        activation_status=activation_status,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the protected RAZZO pre-launch pilot")
    parser.add_argument("--runs", type=int, default=1000)
    parser.add_argument("--output")
    args = parser.parse_args()
    report = run_protected_pilot(simulation_runs=args.runs)
    rendered = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if report.activation_status != "PRELAUNCH_GATES_GREEN":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
