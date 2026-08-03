from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_NODE_RE = re.compile(r"^N[0-9]{3,4}$")
_GLOB_CHARS = frozenset("*?[")


class HomoLevel(IntEnum):
    """HOMO NOVUS software hierarchy, ordered from smallest to largest."""

    ATOM = 1
    MOLECULE = 2
    MACROMOLECULE = 3
    CELL = 4
    TISSUE = 5
    ORGAN = 6
    SYSTEM = 7
    ORGANISM = 8


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _clean(value: str) -> str:
    return " ".join(value.strip().split())


def normalize_surface(surface: str) -> str:
    """Return a safe repository-relative POSIX surface or fail closed.

    Globs are allowed only in the final path segment. Parent traversal,
    absolute paths, platform separators and ambiguous dot segments are rejected.
    """

    value = surface.strip()
    if not value or "\x00" in value:
        raise ValueError("allowed surface cannot be empty or contain NUL")
    if "\\" in value:
        raise ValueError("allowed surface must use POSIX separators")
    if value.startswith("/"):
        raise ValueError("allowed surface must be repository-relative")

    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError("allowed surface contains an ambiguous path segment")
    for part in raw_parts[:-1]:
        if any(ch in part for ch in _GLOB_CHARS):
            raise ValueError("globs are allowed only in the final path segment")

    normalized = PurePosixPath(*raw_parts).as_posix()
    if normalized != value:
        raise ValueError("allowed surface must already be canonically normalized")
    return normalized


def _surface_root(surface: str) -> tuple[str, ...]:
    normalized = normalize_surface(surface)
    parts = list(PurePosixPath(normalized).parts)
    if any(ch in parts[-1] for ch in _GLOB_CHARS):
        parts.pop()
    return tuple(parts)


def surfaces_overlap(left: str, right: str) -> bool:
    """Conservatively classify prefix/glob surface overlap."""

    a = _surface_root(left)
    b = _surface_root(right)
    if not a or not b:
        return True
    prefix = min(len(a), len(b))
    return a[:prefix] == b[:prefix]


@dataclass(frozen=True)
class CapabilitySpec:
    project_id: str
    title: str
    user_outcome: str
    exact_base_sha: str
    acceptance_criteria: tuple[str, ...]
    collision_domains: tuple[str, ...]
    target_level: HomoLevel = HomoLevel.ORGAN
    priority: int = 50

    def validate(self) -> None:
        if not _clean(self.project_id):
            raise ValueError("capability requires project_id")
        if not _clean(self.title) or not _clean(self.user_outcome):
            raise ValueError("capability requires title and user_outcome")
        if not _SHA_RE.fullmatch(self.exact_base_sha):
            raise ValueError("exact_base_sha must be a lowercase 40-character SHA")
        normalized_criteria = tuple(_clean(item) for item in self.acceptance_criteria)
        if len(normalized_criteria) < 2 or any(not item for item in normalized_criteria):
            raise ValueError("capability requires at least two non-empty acceptance criteria")
        if len(set(normalized_criteria)) != len(normalized_criteria):
            raise ValueError("acceptance criteria must be unique")
        normalized_domains = tuple(_clean(item) for item in self.collision_domains)
        if not normalized_domains or any(not item for item in normalized_domains):
            raise ValueError("capability requires non-empty collision domains")
        if len(set(normalized_domains)) != len(normalized_domains):
            raise ValueError("capability collision domains must be unique")
        if not 0 <= self.priority <= 100:
            raise ValueError("priority must be between 0 and 100")

    @property
    def capability_id(self) -> str:
        """Stable logical identity. Deliberately excludes mutable repository SHA."""

        self.validate()
        return _digest(
            {
                "project_id": _clean(self.project_id),
                "title": _clean(self.title).lower(),
                "user_outcome": _clean(self.user_outcome).lower(),
                "acceptance_criteria": sorted(
                    _clean(item).lower() for item in self.acceptance_criteria
                ),
                "target_level": self.target_level.name,
            }
        )


@dataclass(frozen=True)
class CapabilityNode:
    node_id: str
    title: str
    level: HomoLevel
    responsibility: str
    dependencies: tuple[str, ...]
    allowed_surfaces: tuple[str, ...]
    acceptance_subset: tuple[str, ...]
    collision_domain: str
    verification: tuple[str, ...]
    priority: int = 50
    product_value: int = 50
    unlock_value: int = 0
    parallel_value: int = 50
    risk: int = 20
    estimated_cost: int = 1

    def validate(self) -> None:
        if not _NODE_RE.fullmatch(self.node_id):
            raise ValueError(f"invalid capability node id: {self.node_id}")
        if not _clean(self.title) or not _clean(self.responsibility):
            raise ValueError(f"{self.node_id} requires title and responsibility")
        if self.node_id in self.dependencies:
            raise ValueError(f"{self.node_id} cannot depend on itself")
        if len(self.dependencies) != len(set(self.dependencies)):
            raise ValueError(f"{self.node_id} dependencies must be unique")
        if not self.allowed_surfaces:
            raise ValueError(f"{self.node_id} requires allowed surfaces")
        normalized_surfaces = tuple(normalize_surface(item) for item in self.allowed_surfaces)
        if len(normalized_surfaces) != len(set(normalized_surfaces)):
            raise ValueError(f"{self.node_id} allowed surfaces must be unique")
        normalized_subset = tuple(_clean(item) for item in self.acceptance_subset)
        if not normalized_subset or any(not item for item in normalized_subset):
            raise ValueError(f"{self.node_id} requires an acceptance subset")
        if len(normalized_subset) != len(set(normalized_subset)):
            raise ValueError(f"{self.node_id} acceptance subset must be unique")
        if not _clean(self.collision_domain):
            raise ValueError(f"{self.node_id} requires a collision domain")
        normalized_verification = tuple(_clean(item) for item in self.verification)
        if not normalized_verification or any(not item for item in normalized_verification):
            raise ValueError(f"{self.node_id} requires verification commands or assertions")
        for name, value in (
            ("priority", self.priority),
            ("product_value", self.product_value),
            ("unlock_value", self.unlock_value),
            ("parallel_value", self.parallel_value),
            ("risk", self.risk),
        ):
            if not 0 <= value <= 100:
                raise ValueError(f"{self.node_id} {name} must be between 0 and 100")
        if not 1 <= self.estimated_cost <= 100:
            raise ValueError(f"{self.node_id} estimated_cost must be between 1 and 100")

    @property
    def weighted_score(self) -> float:
        """Balanced utility score; no single raw field lexicographically dominates."""

        benefit = (
            self.priority * 0.30
            + self.product_value * 0.30
            + self.unlock_value * 0.20
            + self.parallel_value * 0.20
        )
        penalty = self.risk * 0.30 + self.estimated_cost * 0.70
        return benefit - penalty

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "title": _clean(self.title),
            "level": self.level.name,
            "responsibility": _clean(self.responsibility),
            "dependencies": sorted(self.dependencies),
            "allowed_surfaces": sorted(normalize_surface(x) for x in self.allowed_surfaces),
            "acceptance_subset": sorted(_clean(x) for x in self.acceptance_subset),
            "collision_domain": _clean(self.collision_domain),
            "verification": tuple(_clean(x) for x in self.verification),
            "priority": self.priority,
            "product_value": self.product_value,
            "unlock_value": self.unlock_value,
            "parallel_value": self.parallel_value,
            "risk": self.risk,
            "estimated_cost": self.estimated_cost,
        }


@dataclass(frozen=True)
class CapabilityWave:
    capability_id: str
    revision_id: str
    exact_base_sha: str
    node_ids: tuple[str, ...]
    completed_before: tuple[str, ...]
    display_index: int = 1

    def validate(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.capability_id):
            raise ValueError("wave requires a capability SHA-256 identity")
        if not re.fullmatch(r"[0-9a-f]{64}", self.revision_id):
            raise ValueError("wave requires a revision SHA-256 identity")
        if not _SHA_RE.fullmatch(self.exact_base_sha):
            raise ValueError("wave exact_base_sha must be exact")
        if not self.node_ids or len(self.node_ids) != len(set(self.node_ids)):
            raise ValueError("wave requires unique node IDs")
        if len(self.completed_before) != len(set(self.completed_before)):
            raise ValueError("completed_before must contain unique node IDs")
        if self.display_index < 1:
            raise ValueError("display_index must be positive")

    @property
    def wave_id(self) -> str:
        """Retry-stable identity. Display index is intentionally excluded."""

        self.validate()
        return _digest(
            {
                "capability_id": self.capability_id,
                "revision_id": self.revision_id,
                "exact_base_sha": self.exact_base_sha,
                "node_ids": list(self.node_ids),
                "completed_before": sorted(self.completed_before),
            }
        )


@dataclass(frozen=True)
class CapabilityPlan:
    spec: CapabilitySpec
    nodes: tuple[CapabilityNode, ...]
    _by_id: Mapping[str, CapabilityNode] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_id", {node.node_id: node for node in self.nodes})
        self.validate()

    @property
    def capability_id(self) -> str:
        return self.spec.capability_id

    @property
    def revision_id(self) -> str:
        """Exact repository-bound decomposition identity."""

        return _digest(
            {
                "capability_id": self.capability_id,
                "exact_base_sha": self.spec.exact_base_sha,
                "collision_domains": sorted(_clean(x) for x in self.spec.collision_domains),
                "nodes": [
                    node.canonical_dict()
                    for node in sorted(self.nodes, key=lambda item: item.node_id)
                ],
            }
        )

    def validate(self) -> None:
        self.spec.validate()
        if not self.nodes:
            raise ValueError("capability plan requires at least one node")
        ids = [node.node_id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("capability plan contains duplicate node IDs")

        known = set(ids)
        criteria = {_clean(item) for item in self.spec.acceptance_criteria}
        declared_domains = {_clean(item) for item in self.spec.collision_domains}
        covered: set[str] = set()
        for node in self.nodes:
            node.validate()
            unknown = set(node.dependencies) - known
            if unknown:
                raise ValueError(f"{node.node_id} has unknown dependencies: {sorted(unknown)}")
            subset = {_clean(item) for item in node.acceptance_subset}
            foreign = subset - criteria
            if foreign:
                raise ValueError(
                    f"{node.node_id} references unknown acceptance criteria: {sorted(foreign)}"
                )
            covered.update(subset)
            if _clean(node.collision_domain) not in declared_domains:
                raise ValueError(
                    f"{node.node_id} collision domain is not declared by the capability"
                )

        missing = criteria - covered
        if missing:
            raise ValueError(f"capability acceptance is not fully covered: {sorted(missing)}")
        self._assert_acyclic()
        self._assert_independent_isolation()

    def _assert_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError(f"capability DAG contains a cycle at {node_id}")
            if node_id in visited:
                return
            visiting.add(node_id)
            for dependency in self._by_id[node_id].dependencies:
                visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in sorted(self._by_id):
            visit(node_id)

    def _depends_on(self, node_id: str, ancestor_id: str) -> bool:
        pending = list(self._by_id[node_id].dependencies)
        observed: set[str] = set()
        while pending:
            current = pending.pop()
            if current == ancestor_id:
                return True
            if current in observed:
                continue
            observed.add(current)
            pending.extend(self._by_id[current].dependencies)
        return False

    def _serial(self, left: str, right: str) -> bool:
        return self._depends_on(left, right) or self._depends_on(right, left)

    def _assert_independent_isolation(self) -> None:
        ordered = sorted(self.nodes, key=lambda node: node.node_id)
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                if self._serial(left.node_id, right.node_id):
                    continue
                if _clean(left.collision_domain) == _clean(right.collision_domain):
                    raise ValueError(
                        "independent nodes share a collision domain: "
                        f"{left.node_id} <-> {right.node_id}"
                    )
                for a in left.allowed_surfaces:
                    for b in right.allowed_surfaces:
                        if surfaces_overlap(a, b):
                            raise ValueError(
                                "independent nodes have overlapping allowed surfaces: "
                                f"{left.node_id}:{a} <-> {right.node_id}:{b}"
                            )

    def validate_completed(self, completed_node_ids: Iterable[str]) -> frozenset[str]:
        completed = frozenset(completed_node_ids)
        unknown = completed - set(self._by_id)
        if unknown:
            raise ValueError(f"unknown completed node IDs: {sorted(unknown)}")
        for node_id in completed:
            missing = set(self._by_id[node_id].dependencies) - completed
            if missing:
                raise ValueError(
                    f"completed set is not dependency-closed for {node_id}: {sorted(missing)}"
                )
        return completed

    def topological_order(self) -> tuple[str, ...]:
        indegree = {node.node_id: len(node.dependencies) for node in self.nodes}
        dependents: dict[str, list[str]] = {node.node_id: [] for node in self.nodes}
        for node in self.nodes:
            for dependency in node.dependencies:
                dependents[dependency].append(node.node_id)

        ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
        output: list[str] = []
        while ready:
            current = ready.pop(0)
            output.append(current)
            for dependent in sorted(dependents[current]):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)
                    ready.sort()
        if len(output) != len(self.nodes):
            raise ValueError("capability DAG is not acyclic")
        return tuple(output)

    def completion_ratio(self, completed_node_ids: Iterable[str]) -> float:
        completed = self.validate_completed(completed_node_ids)
        total = sum(node.estimated_cost for node in self.nodes)
        done = sum(
            node.estimated_cost for node in self.nodes if node.node_id in completed
        )
        return done / total

    def next_wave(
        self,
        *,
        completed_node_ids: Iterable[str] = (),
        active_collision_domains: Iterable[str] = (),
        max_workers: int = 5,
        display_index: int = 1,
        exact_base_sha: str | None = None,
    ) -> CapabilityWave | None:
        if not 1 <= max_workers <= 5:
            raise ValueError("current Objective Kernel supports 1..5 builders")
        completed = self.validate_completed(completed_node_ids)
        base_sha = exact_base_sha or self.spec.exact_base_sha
        if not _SHA_RE.fullmatch(base_sha):
            raise ValueError("wave exact_base_sha must be exact")
        active_domains = {_clean(item) for item in active_collision_domains}

        selected: list[CapabilityNode] = []
        selected_ids: set[str] = set()
        selected_domains: set[str] = set()
        remaining = {
            node.node_id: node
            for node in self.nodes
            if node.node_id not in completed
        }

        while remaining and len(selected) < max_workers:
            eligible = [
                node
                for node in remaining.values()
                if set(node.dependencies).issubset(completed | selected_ids)
                and _clean(node.collision_domain) not in active_domains
                and _clean(node.collision_domain) not in selected_domains
            ]
            if not eligible:
                break
            eligible.sort(
                key=lambda node: (node.weighted_score, node.node_id), reverse=True
            )
            chosen = eligible[0]
            selected.append(chosen)
            selected_ids.add(chosen.node_id)
            selected_domains.add(_clean(chosen.collision_domain))
            remaining.pop(chosen.node_id)

        if not selected:
            return None
        wave = CapabilityWave(
            capability_id=self.capability_id,
            revision_id=self.revision_id,
            exact_base_sha=base_sha,
            node_ids=tuple(node.node_id for node in selected),
            completed_before=tuple(sorted(completed)),
            display_index=display_index,
        )
        self.validate_wave(wave)
        return wave

    def validate_wave(self, wave: CapabilityWave) -> tuple[CapabilityNode, ...]:
        wave.validate()
        if wave.capability_id != self.capability_id:
            raise ValueError("wave capability identity mismatch")
        if wave.revision_id != self.revision_id:
            raise ValueError("wave revision identity mismatch")
        if wave.exact_base_sha != self.spec.exact_base_sha:
            raise ValueError("wave exact SHA differs from the compiled plan revision")
        completed = self.validate_completed(wave.completed_before)
        unknown = set(wave.node_ids) - set(self._by_id)
        if unknown:
            raise ValueError(f"wave contains nodes outside the plan: {sorted(unknown)}")
        nodes = tuple(self._by_id[node_id] for node_id in wave.node_ids)
        if len({_clean(node.collision_domain) for node in nodes}) != len(nodes):
            raise ValueError("wave contains duplicate collision domains")
        selected_so_far = set(completed)
        for node in nodes:
            if not set(node.dependencies).issubset(selected_so_far):
                raise ValueError(
                    f"wave ordering does not satisfy dependencies for {node.node_id}"
                )
            selected_so_far.add(node.node_id)
        return nodes

    def to_controller_payload(self, wave: CapabilityWave) -> dict[str, Any]:
        nodes = self.validate_wave(wave)
        selected_ids = set(wave.node_ids)
        shred_ids = {
            node_id: f"S{index:02d}"
            for index, node_id in enumerate(wave.node_ids, start=1)
        }

        acceptance = [
            criterion
            for criterion in self.spec.acceptance_criteria
            if any(criterion in node.acceptance_subset for node in nodes)
        ]
        while len(acceptance) < 2:
            fallback = (
                "The wave preserves repository integrity and exact-SHA verification."
                if not acceptance
                else "The wave remains resumable without duplicate execution."
            )
            if fallback not in acceptance:
                acceptance.append(fallback)

        shreds: list[dict[str, Any]] = []
        for node in nodes:
            shreds.append(
                {
                    "shred_id": shred_ids[node.node_id],
                    "responsibility": node.responsibility,
                    "dependencies": [
                        shred_ids[dependency]
                        for dependency in node.dependencies
                        if dependency in selected_ids
                    ],
                    "allowed_surfaces": [
                        normalize_surface(surface) for surface in node.allowed_surfaces
                    ],
                    "acceptance_subset": list(node.acceptance_subset),
                    "collision_domain": node.collision_domain,
                    "verification": list(node.verification),
                    "capability_node_id": node.node_id,
                    "homo_level": node.level.name,
                }
            )

        return {
            "project_id": self.spec.project_id,
            "base_sha": wave.exact_base_sha,
            "goal": f"{self.spec.title} [wave:{wave.wave_id[:16]}]",
            "user_outcome": self.spec.user_outcome,
            "acceptance_criteria": acceptance,
            "collision_domains": [node.collision_domain for node in nodes],
            "shreds": shreds,
            "metadata": {
                "capability_id": self.capability_id,
                "revision_id": self.revision_id,
                "wave_id": wave.wave_id,
                "display_index": wave.display_index,
                "completed_before": list(wave.completed_before),
                "selected_nodes": list(wave.node_ids),
                "target_level": self.spec.target_level.name,
                "verification_by_node": {
                    node.node_id: list(node.verification) for node in nodes
                },
            },
        }


def compile_capability(
    spec: CapabilitySpec,
    proposed_nodes: Sequence[CapabilityNode],
) -> CapabilityPlan:
    """Fail-closed compiler for an intelligence-produced decomposition proposal."""

    return CapabilityPlan(spec=spec, nodes=tuple(proposed_nodes))
