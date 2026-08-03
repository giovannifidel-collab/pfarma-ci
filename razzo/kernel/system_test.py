from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .coordination import GlobalLease, LeaseState, simulate_trigger_race

_SHA_CHARS = frozenset("0123456789abcdef")


def _exact_sha(value: str, label: str) -> None:
    if not isinstance(value, str) or len(value) != 40 or any(ch not in _SHA_CHARS for ch in value):
        raise ValueError(f"{label} must be an exact lowercase 40-character SHA")


def _candidate_sha(seed: int, project_id: str) -> str:
    return hashlib.sha1(f"{seed}:{project_id}:candidate".encode("utf-8"), usedforsecurity=False).hexdigest()


def _verify_exact_head(candidate_sha: str, product_ci_sha: str, robot_qa_sha: str) -> None:
    for label, value in (
        ("candidate_sha", candidate_sha),
        ("product_ci_sha", product_ci_sha),
        ("robot_qa_sha", robot_qa_sha),
    ):
        _exact_sha(value, label)
    if not candidate_sha == product_ci_sha == robot_qa_sha:
        raise ValueError("candidate, Product CI and Robot QA must use one exact SHA")


@dataclass(frozen=True)
class SystemTestReport:
    status: str
    fixture_only: bool
    product_writes_allowed: bool
    merge_allowed: bool
    protocol_version: int
    enabled_projects: tuple[str, ...]
    simulations: int
    contenders_per_simulation: int
    lease_winners: int
    blocked_contenders: int
    stale_evidence_rejections: int
    duplicate_capabilities: int
    project_selection_counts: dict[str, int]
    paused_dispatches: int
    invariant_violations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "fixture_only": self.fixture_only,
            "product_writes_allowed": self.product_writes_allowed,
            "merge_allowed": self.merge_allowed,
            "protocol_version": self.protocol_version,
            "enabled_projects": list(self.enabled_projects),
            "simulations": self.simulations,
            "contenders_per_simulation": self.contenders_per_simulation,
            "lease_winners": self.lease_winners,
            "blocked_contenders": self.blocked_contenders,
            "stale_evidence_rejections": self.stale_evidence_rejections,
            "duplicate_capabilities": self.duplicate_capabilities,
            "project_selection_counts": self.project_selection_counts,
            "paused_dispatches": self.paused_dispatches,
            "invariant_violations": list(self.invariant_violations),
        }


def _load_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return parsed


def _validate_protocol(protocol: dict[str, Any]) -> int:
    if protocol.get("protocol") != "RAZZO":
        raise ValueError("protocol identity mismatch")
    version = int(protocol.get("protocolVersion", 0))
    if version <= 0:
        raise ValueError("protocolVersion must be positive")
    if protocol.get("sourceOfTruth") != "github":
        raise ValueError("GitHub must remain the source of truth")
    discovery = protocol.get("discovery", {})
    if not discovery.get("dynamicProjects") or not discovery.get("requireEnabled"):
        raise ValueError("portfolio discovery must remain dynamic and enabled-only")
    execution = protocol.get("execution", {})
    for gate in ("collisionCheck", "exactShaVerification", "failClosed", "integrationBackpressure"):
        if execution.get(gate) is not True:
            raise ValueError(f"execution gate {gate} is not enabled")
    return version


def _validate_projects(projects: dict[str, Any]) -> tuple[str, ...]:
    if projects.get("dynamicPortfolio") is not True:
        raise ValueError("portfolio registry must be dynamic")
    enabled: list[str] = []
    repositories: set[str] = set()
    for project in projects.get("projects", []):
        if not isinstance(project, dict) or not project.get("enabled"):
            continue
        project_id = str(project.get("id", ""))
        repository = str(project.get("repository", ""))
        lane = str(project.get("integrationLane", ""))
        if not project_id or not repository or "/" not in repository or not lane:
            raise ValueError("enabled project is missing id, repository or integration lane")
        if project_id in enabled or repository in repositories:
            raise ValueError("enabled portfolio contains duplicate project identity")
        enabled.append(project_id)
        repositories.add(repository)
    if not enabled:
        raise ValueError("portfolio has no enabled projects")
    return tuple(enabled)


def _validate_safe_status(status: dict[str, Any]) -> str:
    state = str(status.get("factory_state", ""))
    if status.get("active_capability") is not None:
        raise ValueError("preflight system test requires no active capability")
    if status.get("capability_state") != "NONE" or status.get("product_receipt") is not None:
        raise ValueError("preflight system test requires no product receipt")
    heartbeat = status.get("last_heartbeat", {})
    if not isinstance(heartbeat, dict):
        raise ValueError("last heartbeat must be an object")
    if heartbeat.get("run_id") is not None:
        raise ValueError("preflight system test requires an ownerless heartbeat")
    if state == "PAUSED":
        if status.get("enabled_cells") != []:
            raise ValueError("paused Factory cannot have enabled cells")
        if heartbeat.get("state") != "DISABLED":
            raise ValueError("paused Factory heartbeat must be disabled")
    elif state == "RUNNING":
        if status.get("enabled_cells") != ["RAZZO-Cell-00"]:
            raise ValueError("protected pilot must enable exactly RAZZO-Cell-00")
        if heartbeat.get("state") != "SCHEDULED":
            raise ValueError("protected pilot preflight heartbeat must be scheduled")
    else:
        raise ValueError("system test supports only PAUSED or protected RUNNING preflight state")
    _exact_sha(str(status.get("control_plane_sha", "")), "factory status control_plane_sha")
    return state


def run_total_system_test(
    *,
    protocol_path: Path,
    projects_path: Path,
    status_path: Path,
    lease_path: Path,
    runs: int,
    contenders: int,
) -> SystemTestReport:
    if runs < 1 or contenders < 2:
        raise ValueError("runs must be positive and contenders must be at least two")
    protocol = _load_json(protocol_path)
    projects = _load_json(projects_path)
    status = _load_json(status_path)
    lease = GlobalLease.from_dict(_load_json(lease_path))
    protocol_version = _validate_protocol(protocol)
    enabled_projects = _validate_projects(projects)
    _validate_safe_status(status)
    if lease.state is not LeaseState.FREE:
        raise ValueError("global lease must be free during non-mutating preflight simulation")

    violations: list[str] = []
    winners = 0
    blocked = 0
    stale_rejections = 0
    duplicate_capabilities = 0
    paused_dispatches = 0
    selection_counts = {project_id: 0 for project_id in enabled_projects}
    contender_ids = tuple(f"RAZZO-Cell-{index:02d}" for index in range(contenders))
    now = datetime(2026, 8, 3, 20, 23, tzinfo=timezone.utc)

    for seed in range(runs):
        order = list(range(contenders))
        random.Random(seed).shuffle(order)
        try:
            race = simulate_trigger_race(
                lease,
                contenders=contender_ids,
                attempt_order=order,
                now=now,
            )
            winners += 1
            blocked += len(race.blocked_runs)
            if len(set((race.winner, *race.blocked_runs))) != contenders:
                duplicate_capabilities += 1
                violations.append(f"seed {seed}: contender accounting mismatch")

            project_id = enabled_projects[seed % len(enabled_projects)]
            selection_counts[project_id] += 1
            candidate = _candidate_sha(seed, project_id)
            stale = _candidate_sha(seed + runs + 1, project_id)
            try:
                _verify_exact_head(candidate, candidate, stale)
            except ValueError:
                stale_rejections += 1
            else:
                violations.append(f"seed {seed}: stale Robot QA evidence was accepted")
            _verify_exact_head(candidate, candidate, candidate)
        except Exception as exc:
            if len(violations) < 20:
                violations.append(f"seed {seed}: {type(exc).__name__}: {exc}")

    expected_blocked = runs * (contenders - 1)
    if winners != runs:
        violations.append(f"lease winners {winners} != simulations {runs}")
    if blocked != expected_blocked:
        violations.append(f"blocked contenders {blocked} != expected {expected_blocked}")
    if stale_rejections != runs:
        violations.append(f"stale evidence rejections {stale_rejections} != simulations {runs}")
    if any(count == 0 for count in selection_counts.values()):
        violations.append("portfolio fairness simulation skipped an enabled project")
    if paused_dispatches != 0:
        violations.append("non-mutating simulation produced an unauthorized dispatch")

    status_name = "SYSTEM_SIMULATION_GREEN" if not violations else "SYSTEM_SIMULATION_FAILED"
    return SystemTestReport(
        status=status_name,
        fixture_only=True,
        product_writes_allowed=False,
        merge_allowed=False,
        protocol_version=protocol_version,
        enabled_projects=enabled_projects,
        simulations=runs,
        contenders_per_simulation=contenders,
        lease_winners=winners,
        blocked_contenders=blocked,
        stale_evidence_rejections=stale_rejections,
        duplicate_capabilities=duplicate_capabilities,
        project_selection_counts=selection_counts,
        paused_dispatches=paused_dispatches,
        invariant_violations=tuple(violations),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the non-mutating RAZZO total system simulation")
    parser.add_argument("--protocol", type=Path, default=Path("razzo/protocol.json"))
    parser.add_argument("--projects", type=Path, default=Path("razzo/projects.json"))
    parser.add_argument("--status", type=Path, default=Path("razzo/state/factory-status.json"))
    parser.add_argument("--lease", type=Path, default=Path("razzo/state/global-lease.json"))
    parser.add_argument("--runs", type=int, default=1000)
    parser.add_argument("--contenders", type=int, default=5)
    parser.add_argument("--report", type=Path)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = run_total_system_test(
        protocol_path=args.protocol,
        projects_path=args.projects,
        status_path=args.status,
        lease_path=args.lease,
        runs=args.runs,
        contenders=args.contenders,
    )
    encoded = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    print(encoded, end="")
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
    return 0 if report.status == "SYSTEM_SIMULATION_GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
