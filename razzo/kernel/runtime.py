from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


class ExecutionMode(str, Enum):
    SHADOW = "SHADOW"
    SANDBOX = "SANDBOX"
    PILOT = "PILOT"
    PRODUCTION = "PRODUCTION"


@dataclass(frozen=True)
class ActivationPolicy:
    mode: ExecutionMode
    provider_eligible: bool
    human_gate_approved: bool = False
    product_writes_allowed: bool = False
    merge_allowed: bool = False
    fixture_only: bool = False

    def validate(self) -> None:
        if self.mode is ExecutionMode.SHADOW:
            if self.product_writes_allowed or self.merge_allowed:
                raise ValueError("shadow mode cannot write or merge")
        elif self.mode is ExecutionMode.SANDBOX:
            if not self.fixture_only or self.product_writes_allowed or self.merge_allowed:
                raise ValueError("sandbox mode must be fixture-only and non-mutating")
        elif self.mode is ExecutionMode.PILOT:
            if self.merge_allowed:
                raise ValueError("pilot mode cannot auto-merge")
            if self.product_writes_allowed and not self.human_gate_approved:
                raise ValueError("pilot product writes require an explicit human gate")
        elif self.mode is ExecutionMode.PRODUCTION:
            if not self.provider_eligible:
                raise ValueError("production requires an eligible execution provider")
            if not self.human_gate_approved:
                raise ValueError("production activation requires human approval")
            if not self.product_writes_allowed:
                raise ValueError("production activation must explicitly allow product writes")
        else:
            raise ValueError("unsupported execution mode")


class NodeState(str, Enum):
    PLANNED = "PLANNED"
    LEASED = "LEASED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class WaveState(str, Enum):
    PLANNED = "PLANNED"
    BUILDING = "BUILDING"
    ASSEMBLING = "ASSEMBLING"
    VERIFYING = "VERIFYING"
    MERGE_READY = "MERGE_READY"
    MERGED = "MERGED"
    NEEDS_REPLAN = "NEEDS_REPLAN"
    FAILED = "FAILED"


@dataclass(frozen=True)
class RuntimeEvent:
    event_type: str
    capability_id: str
    revision_id: str
    wave_id: str
    exact_sha: str
    node_id: str | None = None
    collision_domain: str | None = None
    payload: tuple[tuple[str, str], ...] = ()

    def validate(self) -> None:
        for value, label in (
            (self.capability_id, "capability_id"),
            (self.revision_id, "revision_id"),
            (self.wave_id, "wave_id"),
        ):
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError(f"{label} must be a lowercase SHA-256")
        if not _SHA_RE.fullmatch(self.exact_sha):
            raise ValueError("runtime event requires an exact lowercase SHA")
        if not self.event_type.strip():
            raise ValueError("runtime event requires event_type")
        if self.node_id is not None and not re.fullmatch(r"N[0-9]{3,4}", self.node_id):
            raise ValueError("runtime event node_id is invalid")
        if self.collision_domain is not None and not self.collision_domain.strip():
            raise ValueError("runtime event collision_domain cannot be empty")
        keys = [key for key, _ in self.payload]
        if len(keys) != len(set(keys)):
            raise ValueError("runtime event payload keys must be unique")

    @property
    def event_id(self) -> str:
        self.validate()
        return _digest(
            {
                "event_type": self.event_type,
                "capability_id": self.capability_id,
                "revision_id": self.revision_id,
                "wave_id": self.wave_id,
                "exact_sha": self.exact_sha,
                "node_id": self.node_id,
                "collision_domain": self.collision_domain,
                "payload": list(self.payload),
            }
        )


@dataclass(frozen=True)
class RuntimeSnapshot:
    capability_id: str
    revision_id: str
    wave_id: str
    exact_sha: str
    wave_state: WaveState
    node_states: tuple[tuple[str, NodeState], ...]
    active_leases: tuple[tuple[str, str], ...]
    product_ci_sha: str | None
    robot_qa_sha: str | None
    candidate_sha: str | None
    merged_sha: str | None
    applied_events: tuple[str, ...]


@dataclass
class RuntimeJournal:
    capability_id: str
    revision_id: str
    wave_id: str
    exact_sha: str
    node_ids: tuple[str, ...]
    policy: ActivationPolicy
    wave_state: WaveState = WaveState.PLANNED
    node_states: dict[str, NodeState] = field(default_factory=dict)
    active_leases: dict[str, str] = field(default_factory=dict)
    candidate_sha: str | None = None
    product_ci_sha: str | None = None
    robot_qa_sha: str | None = None
    merged_sha: str | None = None
    _applied_events: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        self.policy.validate()
        if not re.fullmatch(r"[0-9a-f]{64}", self.capability_id):
            raise ValueError("journal capability_id must be a SHA-256")
        if not re.fullmatch(r"[0-9a-f]{64}", self.revision_id):
            raise ValueError("journal revision_id must be a SHA-256")
        if not re.fullmatch(r"[0-9a-f]{64}", self.wave_id):
            raise ValueError("journal wave_id must be a SHA-256")
        if not _SHA_RE.fullmatch(self.exact_sha):
            raise ValueError("journal exact_sha must be exact")
        if not self.node_ids or len(self.node_ids) != len(set(self.node_ids)):
            raise ValueError("journal requires unique node_ids")
        if not self.node_states:
            self.node_states = {node_id: NodeState.PLANNED for node_id in self.node_ids}
        elif set(self.node_states) != set(self.node_ids):
            raise ValueError("journal node_states do not match node_ids")

    def _assert_event_scope(self, event: RuntimeEvent) -> None:
        event.validate()
        if (
            event.capability_id != self.capability_id
            or event.revision_id != self.revision_id
            or event.wave_id != self.wave_id
        ):
            raise ValueError("runtime event scope mismatch")
        if event.exact_sha != self.exact_sha:
            raise ValueError("runtime event exact SHA mismatch")
        if event.node_id is not None and event.node_id not in self.node_states:
            raise ValueError("runtime event references an unknown node")

    def apply(self, event: RuntimeEvent) -> bool:
        """Apply once. Returns False for an exact duplicate event."""

        self._assert_event_scope(event)
        event_id = event.event_id
        if event_id in self._applied_events:
            return False

        handlers = {
            "WAVE_STARTED": self._wave_started,
            "NODE_LEASED": self._node_leased,
            "NODE_SUCCEEDED": self._node_succeeded,
            "NODE_FAILED": self._node_failed,
            "ASSEMBLY_STARTED": self._assembly_started,
            "CANDIDATE_CREATED": self._candidate_created,
            "PRODUCT_CI_PASSED": self._product_ci_passed,
            "ROBOT_QA_PASSED": self._robot_qa_passed,
            "MERGE_READY": self._merge_ready,
            "MERGED": self._merged,
            "NEEDS_REPLAN": self._needs_replan,
        }
        handler = handlers.get(event.event_type)
        if handler is None:
            raise ValueError(f"unsupported runtime event type: {event.event_type}")
        handler(event)
        self._applied_events.add(event_id)
        return True

    def _wave_started(self, event: RuntimeEvent) -> None:
        if self.wave_state is not WaveState.PLANNED:
            raise ValueError("wave can start only from PLANNED")
        self.wave_state = WaveState.BUILDING

    def _node_leased(self, event: RuntimeEvent) -> None:
        if self.wave_state is not WaveState.BUILDING or event.node_id is None:
            raise ValueError("node lease requires BUILDING state and node_id")
        if self.node_states[event.node_id] is not NodeState.PLANNED:
            raise ValueError("only a planned node may be leased")
        if not event.collision_domain:
            raise ValueError("node lease requires collision domain")
        if event.collision_domain in self.active_leases.values():
            raise ValueError("collision domain already has an active lease")
        self.node_states[event.node_id] = NodeState.LEASED
        self.active_leases[event.node_id] = event.collision_domain

    def _node_succeeded(self, event: RuntimeEvent) -> None:
        if event.node_id is None or self.node_states[event.node_id] is not NodeState.LEASED:
            raise ValueError("only a leased node may succeed")
        self.node_states[event.node_id] = NodeState.SUCCEEDED
        self.active_leases.pop(event.node_id, None)

    def _node_failed(self, event: RuntimeEvent) -> None:
        if event.node_id is None or self.node_states[event.node_id] is not NodeState.LEASED:
            raise ValueError("only a leased node may fail")
        self.node_states[event.node_id] = NodeState.FAILED
        self.active_leases.pop(event.node_id, None)
        self.wave_state = WaveState.NEEDS_REPLAN

    def _assembly_started(self, event: RuntimeEvent) -> None:
        if self.wave_state is not WaveState.BUILDING:
            raise ValueError("assembly requires BUILDING state")
        if any(state is not NodeState.SUCCEEDED for state in self.node_states.values()):
            raise ValueError("assembly requires every node to succeed")
        if self.active_leases:
            raise ValueError("assembly requires all leases to be released")
        self.wave_state = WaveState.ASSEMBLING

    def _payload(self, event: RuntimeEvent) -> dict[str, str]:
        return dict(event.payload)

    def _candidate_created(self, event: RuntimeEvent) -> None:
        if self.wave_state is not WaveState.ASSEMBLING:
            raise ValueError("candidate creation requires ASSEMBLING state")
        candidate_sha = self._payload(event).get("candidate_sha", "")
        if not _SHA_RE.fullmatch(candidate_sha):
            raise ValueError("candidate creation requires exact candidate_sha")
        self.candidate_sha = candidate_sha
        self.wave_state = WaveState.VERIFYING

    def _product_ci_passed(self, event: RuntimeEvent) -> None:
        if self.wave_state is not WaveState.VERIFYING or self.candidate_sha is None:
            raise ValueError("Product CI requires VERIFYING state and candidate")
        tested_sha = self._payload(event).get("tested_sha", "")
        if tested_sha != self.candidate_sha:
            raise ValueError("Product CI did not verify the candidate exact SHA")
        self.product_ci_sha = tested_sha

    def _robot_qa_passed(self, event: RuntimeEvent) -> None:
        if self.wave_state is not WaveState.VERIFYING or self.candidate_sha is None:
            raise ValueError("Robot QA requires VERIFYING state and candidate")
        tested_sha = self._payload(event).get("tested_sha", "")
        if tested_sha != self.candidate_sha:
            raise ValueError("Robot QA did not verify the candidate exact SHA")
        self.robot_qa_sha = tested_sha

    def _merge_ready(self, event: RuntimeEvent) -> None:
        if self.wave_state is not WaveState.VERIFYING or self.candidate_sha is None:
            raise ValueError("merge-ready requires VERIFYING state")
        if not (
            self.product_ci_sha == self.candidate_sha
            and self.robot_qa_sha == self.candidate_sha
        ):
            raise ValueError("merge-ready requires CI and QA on the candidate exact SHA")
        self.wave_state = WaveState.MERGE_READY

    def _merged(self, event: RuntimeEvent) -> None:
        if self.wave_state is not WaveState.MERGE_READY:
            raise ValueError("merge requires MERGE_READY state")
        self.policy.validate()
        if not self.policy.merge_allowed:
            raise ValueError("current activation policy forbids merge")
        merged_sha = self._payload(event).get("merged_sha", "")
        if not _SHA_RE.fullmatch(merged_sha):
            raise ValueError("merge event requires exact merged_sha")
        self.merged_sha = merged_sha
        self.wave_state = WaveState.MERGED

    def _needs_replan(self, event: RuntimeEvent) -> None:
        if self.wave_state in {WaveState.MERGED, WaveState.FAILED}:
            raise ValueError("terminal wave cannot replan")
        self.active_leases.clear()
        self.wave_state = WaveState.NEEDS_REPLAN

    def snapshot(self) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            capability_id=self.capability_id,
            revision_id=self.revision_id,
            wave_id=self.wave_id,
            exact_sha=self.exact_sha,
            wave_state=self.wave_state,
            node_states=tuple(sorted(self.node_states.items())),
            active_leases=tuple(sorted(self.active_leases.items())),
            product_ci_sha=self.product_ci_sha,
            robot_qa_sha=self.robot_qa_sha,
            candidate_sha=self.candidate_sha,
            merged_sha=self.merged_sha,
            applied_events=tuple(sorted(self._applied_events)),
        )

    @classmethod
    def replay(
        cls,
        *,
        capability_id: str,
        revision_id: str,
        wave_id: str,
        exact_sha: str,
        node_ids: Iterable[str],
        policy: ActivationPolicy,
        events: Iterable[RuntimeEvent],
    ) -> "RuntimeJournal":
        journal = cls(
            capability_id=capability_id,
            revision_id=revision_id,
            wave_id=wave_id,
            exact_sha=exact_sha,
            node_ids=tuple(node_ids),
            policy=policy,
        )
        for event in events:
            journal.apply(event)
        return journal
