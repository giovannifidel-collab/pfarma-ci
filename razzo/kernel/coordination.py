from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be RFC3339 UTC with Z suffix")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("timestamp must be valid RFC3339 UTC") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be UTC")
    return parsed


def format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_id(value: str, label: str) -> None:
    if not isinstance(value, str) or not _SAFE_ID_RE.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _exact_sha(value: str, label: str) -> None:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise ValueError(f"{label} must be an exact lowercase 40-character SHA")


class LeaseState(str, Enum):
    FREE = "FREE"
    HELD = "HELD"


class LeaseHeld(RuntimeError):
    pass


class LeaseConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class GlobalLease:
    schema_version: int
    generation: int
    state: LeaseState
    updated_at: str
    control_plane_sha: str
    owner_run_id: str | None = None
    acquired_at: str | None = None
    expires_at: str | None = None
    capability_fingerprint: str | None = None
    canonical_repository: str | None = None
    canonical_pr: int | None = None
    terminal_reason: str | None = None

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported global lease schema")
        if self.generation < 0:
            raise ValueError("generation cannot be negative")
        updated = parse_utc(self.updated_at)
        _exact_sha(self.control_plane_sha, "control_plane_sha")
        if self.terminal_reason is not None:
            _safe_id(self.terminal_reason, "terminal_reason")

        capability_values = (
            self.capability_fingerprint,
            self.canonical_repository,
            self.canonical_pr,
        )
        capability_count = sum(value is not None for value in capability_values)
        if capability_count not in (0, 3):
            raise ValueError("capability binding must be complete or absent")
        if self.capability_fingerprint is not None:
            _safe_id(self.capability_fingerprint, "capability_fingerprint")
            if not _REPOSITORY_RE.fullmatch(str(self.canonical_repository)):
                raise ValueError("canonical_repository must be owner/name")
            if not isinstance(self.canonical_pr, int) or self.canonical_pr <= 0:
                raise ValueError("canonical_pr must be positive")

        if self.state is LeaseState.FREE:
            if any(value is not None for value in (
                self.owner_run_id,
                self.acquired_at,
                self.expires_at,
                self.capability_fingerprint,
                self.canonical_repository,
                self.canonical_pr,
            )):
                raise ValueError("free lease cannot retain an owner or capability")
            return

        if self.owner_run_id is None or self.acquired_at is None or self.expires_at is None:
            raise ValueError("held lease requires owner, acquired_at and expires_at")
        _safe_id(self.owner_run_id, "owner_run_id")
        acquired = parse_utc(self.acquired_at)
        expires = parse_utc(self.expires_at)
        if not acquired <= updated < expires:
            raise ValueError("held lease timestamps are inconsistent")
        if self.terminal_reason is not None:
            raise ValueError("held lease cannot have terminal_reason")

    def is_active(self, now: datetime) -> bool:
        self.validate()
        return self.state is LeaseState.HELD and now.astimezone(timezone.utc) < parse_utc(str(self.expires_at))

    def acquire(
        self,
        *,
        run_id: str,
        now: datetime,
        ttl_seconds: int,
        control_plane_sha: str,
    ) -> "GlobalLease":
        _safe_id(run_id, "run_id")
        _exact_sha(control_plane_sha, "control_plane_sha")
        if not 60 <= ttl_seconds <= 7200:
            raise ValueError("ttl_seconds must be between 60 and 7200")
        now_utc = now.astimezone(timezone.utc)
        if self.is_active(now_utc):
            if self.owner_run_id == run_id:
                return self
            raise LeaseHeld(f"global lease held by {self.owner_run_id}")
        acquired_at = format_utc(now_utc)
        lease = GlobalLease(
            schema_version=1,
            generation=self.generation + 1,
            state=LeaseState.HELD,
            updated_at=acquired_at,
            control_plane_sha=control_plane_sha,
            owner_run_id=run_id,
            acquired_at=acquired_at,
            expires_at=format_utc(now_utc + timedelta(seconds=ttl_seconds)),
        )
        lease.validate()
        return lease

    def bind_capability(
        self,
        *,
        run_id: str,
        now: datetime,
        capability_fingerprint: str,
        repository: str,
        pull_request: int,
    ) -> "GlobalLease":
        now_utc = now.astimezone(timezone.utc)
        if not self.is_active(now_utc) or self.owner_run_id != run_id:
            raise LeaseHeld("run does not own an active global lease")
        requested = (capability_fingerprint, repository, pull_request)
        existing = (self.capability_fingerprint, self.canonical_repository, self.canonical_pr)
        if self.capability_fingerprint is not None:
            if existing == requested:
                return self
            raise LeaseConflict("lease is already bound to a different capability")
        bound = GlobalLease(
            **{
                **self.to_dict(),
                "generation": self.generation + 1,
                "updated_at": format_utc(now_utc),
                "capability_fingerprint": capability_fingerprint,
                "canonical_repository": repository,
                "canonical_pr": pull_request,
                "state": LeaseState.HELD,
            }
        )
        bound.validate()
        return bound

    def release(self, *, run_id: str, now: datetime, reason: str) -> "GlobalLease":
        now_utc = now.astimezone(timezone.utc)
        if self.state is not LeaseState.HELD or self.owner_run_id != run_id:
            raise LeaseHeld("run does not own the global lease")
        _safe_id(reason, "reason")
        released = GlobalLease(
            schema_version=1,
            generation=self.generation + 1,
            state=LeaseState.FREE,
            updated_at=format_utc(now_utc),
            control_plane_sha=self.control_plane_sha,
            terminal_reason=reason,
        )
        released.validate()
        return released

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "generation": self.generation,
            "state": self.state.value,
            "updated_at": self.updated_at,
            "control_plane_sha": self.control_plane_sha,
            "owner_run_id": self.owner_run_id,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
            "capability_fingerprint": self.capability_fingerprint,
            "canonical_repository": self.canonical_repository,
            "canonical_pr": self.canonical_pr,
            "terminal_reason": self.terminal_reason,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GlobalLease":
        lease = cls(
            schema_version=int(value["schema_version"]),
            generation=int(value["generation"]),
            state=LeaseState(str(value["state"])),
            updated_at=str(value["updated_at"]),
            control_plane_sha=str(value["control_plane_sha"]),
            owner_run_id=None if value.get("owner_run_id") is None else str(value["owner_run_id"]),
            acquired_at=None if value.get("acquired_at") is None else str(value["acquired_at"]),
            expires_at=None if value.get("expires_at") is None else str(value["expires_at"]),
            capability_fingerprint=None if value.get("capability_fingerprint") is None else str(value["capability_fingerprint"]),
            canonical_repository=None if value.get("canonical_repository") is None else str(value["canonical_repository"]),
            canonical_pr=None if value.get("canonical_pr") is None else int(value["canonical_pr"]),
            terminal_reason=None if value.get("terminal_reason") is None else str(value["terminal_reason"]),
        )
        lease.validate()
        return lease


class GlobalLeaseStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> GlobalLease:
        return GlobalLease.from_dict(json.loads(self.path.read_text(encoding="utf-8")))

    def compare_and_swap(self, *, expected_generation: int, lease: GlobalLease) -> None:
        lease.validate()
        current = self.load()
        if current.generation != expected_generation or lease.generation != expected_generation + 1:
            raise LeaseConflict("global lease generation conflict")
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(lease.to_dict(), handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


@dataclass(frozen=True)
class RaceResult:
    winner: str
    blocked_runs: tuple[str, ...]
    final_generation: int


def simulate_trigger_race(
    initial: GlobalLease,
    *,
    contenders: Sequence[str],
    attempt_order: Sequence[int],
    now: datetime,
    ttl_seconds: int = 900,
) -> RaceResult:
    if len(contenders) < 2 or sorted(attempt_order) != list(range(len(contenders))):
        raise ValueError("race requires a permutation of at least two contenders")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "global-lease.json"
        path.write_text(json.dumps(initial.to_dict()), encoding="utf-8")
        store = GlobalLeaseStore(path)
        snapshots = [store.load() for _ in contenders]
        winner: str | None = None
        blocked: list[str] = []
        for index in attempt_order:
            run_id = contenders[index]
            candidate = snapshots[index].acquire(
                run_id=run_id,
                now=now,
                ttl_seconds=ttl_seconds,
                control_plane_sha=initial.control_plane_sha,
            )
            try:
                store.compare_and_swap(expected_generation=snapshots[index].generation, lease=candidate)
                if winner is not None:
                    raise AssertionError("multiple global lease winners")
                winner = run_id
            except LeaseConflict:
                observed = store.load()
                try:
                    observed.acquire(
                        run_id=run_id,
                        now=now,
                        ttl_seconds=ttl_seconds,
                        control_plane_sha=initial.control_plane_sha,
                    )
                except LeaseHeld:
                    blocked.append(run_id)
                else:
                    raise AssertionError("losing contender acquired an active lease")
        if winner is None or len(blocked) != len(contenders) - 1:
            raise AssertionError("race did not converge to one winner")
        return RaceResult(winner=winner, blocked_runs=tuple(sorted(blocked)), final_generation=store.load().generation)
