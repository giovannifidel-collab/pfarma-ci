from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Iterable

from .capability import CapabilityPlan
from .runtime import ActivationPolicy, ExecutionMode, RuntimeEvent, RuntimeJournal, WaveState


def _sha(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()


@dataclass(frozen=True)
class FaultProfile:
    node_failure_rate: float = 0.03
    duplicate_event_rate: float = 0.05
    stale_ci_rate: float = 0.02
    stale_qa_rate: float = 0.02
    crash_replay_rate: float = 0.08

    def validate(self) -> None:
        for name, value in self.__dict__.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class SimulationResult:
    seed: int
    completed_nodes: tuple[str, ...]
    wave_count: int
    retry_count: int
    rejected_stale_evidence: int
    duplicate_events_ignored: int
    invariant_violations: tuple[str, ...]
    terminal_state: str

    @property
    def success(self) -> bool:
        return not self.invariant_violations and self.terminal_state == "CAPABILITY_COMPLETE"


@dataclass(frozen=True)
class CampaignResult:
    runs: int
    successes: int
    failures: int
    total_retries: int
    total_stale_rejections: int
    total_duplicate_ignores: int
    invariant_failure_examples: tuple[str, ...]

    @property
    def success_rate(self) -> float:
        return self.successes / self.runs if self.runs else 0.0


def _event(
    *,
    event_type: str,
    plan: CapabilityPlan,
    wave_id: str,
    exact_sha: str,
    node_id: str | None = None,
    collision_domain: str | None = None,
    **payload: str,
) -> RuntimeEvent:
    return RuntimeEvent(
        event_type=event_type,
        capability_id=plan.capability_id,
        revision_id=plan.revision_id,
        wave_id=wave_id,
        exact_sha=exact_sha,
        node_id=node_id,
        collision_domain=collision_domain,
        payload=tuple(sorted(payload.items())),
    )


def simulate_once(
    plan: CapabilityPlan,
    *,
    seed: int,
    fault_profile: FaultProfile | None = None,
    max_workers: int = 5,
) -> SimulationResult:
    profile = fault_profile or FaultProfile()
    profile.validate()
    rng = random.Random(seed)
    completed: set[str] = set()
    retry_count = 0
    stale_rejections = 0
    duplicate_ignores = 0
    wave_count = 0
    invariant_violations: list[str] = []

    while len(completed) < len(plan.nodes):
        wave_count += 1
        wave = plan.next_wave(
            completed_node_ids=completed,
            max_workers=max_workers,
            display_index=wave_count,
        )
        if wave is None:
            invariant_violations.append("scheduler returned no wave before capability completion")
            break
        nodes = plan.validate_wave(wave)
        policy = ActivationPolicy(
            mode=ExecutionMode.SANDBOX,
            provider_eligible=False,
            fixture_only=True,
        )
        journal = RuntimeJournal(
            capability_id=plan.capability_id,
            revision_id=plan.revision_id,
            wave_id=wave.wave_id,
            exact_sha=wave.exact_base_sha,
            node_ids=wave.node_ids,
            policy=policy,
        )
        events: list[RuntimeEvent] = []

        start = _event(
            event_type="WAVE_STARTED",
            plan=plan,
            wave_id=wave.wave_id,
            exact_sha=wave.exact_base_sha,
        )
        journal.apply(start)
        events.append(start)

        failed = False
        for node in nodes:
            leased = _event(
                event_type="NODE_LEASED",
                plan=plan,
                wave_id=wave.wave_id,
                exact_sha=wave.exact_base_sha,
                node_id=node.node_id,
                collision_domain=node.collision_domain,
            )
            journal.apply(leased)
            events.append(leased)
            if rng.random() < profile.duplicate_event_rate:
                if not journal.apply(leased):
                    duplicate_ignores += 1

            if rng.random() < profile.node_failure_rate:
                failure = _event(
                    event_type="NODE_FAILED",
                    plan=plan,
                    wave_id=wave.wave_id,
                    exact_sha=wave.exact_base_sha,
                    node_id=node.node_id,
                )
                journal.apply(failure)
                events.append(failure)
                retry_count += 1
                failed = True
                break

            success = _event(
                event_type="NODE_SUCCEEDED",
                plan=plan,
                wave_id=wave.wave_id,
                exact_sha=wave.exact_base_sha,
                node_id=node.node_id,
            )
            journal.apply(success)
            events.append(success)
            if rng.random() < profile.duplicate_event_rate:
                if not journal.apply(success):
                    duplicate_ignores += 1

        if rng.random() < profile.crash_replay_rate:
            replayed = RuntimeJournal.replay(
                capability_id=plan.capability_id,
                revision_id=plan.revision_id,
                wave_id=wave.wave_id,
                exact_sha=wave.exact_base_sha,
                node_ids=wave.node_ids,
                policy=policy,
                events=events,
            )
            if replayed.snapshot().wave_state != journal.snapshot().wave_state:
                invariant_violations.append("crash replay changed wave state")
                break
            journal = replayed

        if failed:
            continue

        try:
            journal.apply(
                _event(
                    event_type="ASSEMBLY_STARTED",
                    plan=plan,
                    wave_id=wave.wave_id,
                    exact_sha=wave.exact_base_sha,
                )
            )
        except ValueError as exc:
            invariant_violations.append(f"assembly invariant failed: {exc}")
            break

        candidate_sha = _sha(f"candidate:{plan.revision_id}:{wave.wave_id}")
        journal.apply(
            _event(
                event_type="CANDIDATE_CREATED",
                plan=plan,
                wave_id=wave.wave_id,
                exact_sha=wave.exact_base_sha,
                candidate_sha=candidate_sha,
            )
        )

        ci_sha = (
            _sha(f"stale-ci:{seed}:{wave_count}")
            if rng.random() < profile.stale_ci_rate
            else candidate_sha
        )
        try:
            journal.apply(
                _event(
                    event_type="PRODUCT_CI_PASSED",
                    plan=plan,
                    wave_id=wave.wave_id,
                    exact_sha=wave.exact_base_sha,
                    tested_sha=ci_sha,
                )
            )
        except ValueError:
            stale_rejections += 1
            retry_count += 1
            continue

        qa_sha = (
            _sha(f"stale-qa:{seed}:{wave_count}")
            if rng.random() < profile.stale_qa_rate
            else candidate_sha
        )
        try:
            journal.apply(
                _event(
                    event_type="ROBOT_QA_PASSED",
                    plan=plan,
                    wave_id=wave.wave_id,
                    exact_sha=wave.exact_base_sha,
                    tested_sha=qa_sha,
                )
            )
        except ValueError:
            stale_rejections += 1
            retry_count += 1
            continue

        journal.apply(
            _event(
                event_type="MERGE_READY",
                plan=plan,
                wave_id=wave.wave_id,
                exact_sha=wave.exact_base_sha,
            )
        )
        if journal.wave_state is not WaveState.MERGE_READY:
            invariant_violations.append("exact-head evidence did not reach MERGE_READY")
            break

        completed.update(wave.node_ids)
        try:
            plan.validate_completed(completed)
        except ValueError as exc:
            invariant_violations.append(f"completion closure failed: {exc}")
            break

    terminal = (
        "CAPABILITY_COMPLETE"
        if len(completed) == len(plan.nodes) and not invariant_violations
        else "FAILED"
    )
    return SimulationResult(
        seed=seed,
        completed_nodes=tuple(sorted(completed)),
        wave_count=wave_count,
        retry_count=retry_count,
        rejected_stale_evidence=stale_rejections,
        duplicate_events_ignored=duplicate_ignores,
        invariant_violations=tuple(invariant_violations),
        terminal_state=terminal,
    )


def run_campaign(
    plan: CapabilityPlan,
    *,
    seeds: Iterable[int],
    fault_profile: FaultProfile | None = None,
    max_workers: int = 5,
) -> CampaignResult:
    results = [
        simulate_once(
            plan,
            seed=seed,
            fault_profile=fault_profile,
            max_workers=max_workers,
        )
        for seed in seeds
    ]
    examples: list[str] = []
    for result in results:
        for violation in result.invariant_violations:
            if violation not in examples:
                examples.append(violation)
            if len(examples) >= 10:
                break
    successes = sum(result.success for result in results)
    return CampaignResult(
        runs=len(results),
        successes=successes,
        failures=len(results) - successes,
        total_retries=sum(result.retry_count for result in results),
        total_stale_rejections=sum(result.rejected_stale_evidence for result in results),
        total_duplicate_ignores=sum(result.duplicate_events_ignored for result in results),
        invariant_failure_examples=tuple(examples),
    )
