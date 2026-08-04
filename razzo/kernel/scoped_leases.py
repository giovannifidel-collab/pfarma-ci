from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Iterable


@dataclass(frozen=True)
class Lease:
    repository: str
    collision_domain: str
    owner_run_id: str
    acquired_at: datetime
    expires_at: datetime
    generation: int = 1

    @property
    def key(self) -> tuple[str, str]:
        return (self.repository, self.collision_domain)

    def expired(self, now: datetime) -> bool:
        return self.expires_at <= now


class LeaseConflict(RuntimeError):
    pass


class ScopedLeaseTable:
    """Fail-closed lease table allowing one independent capability per repository/domain."""

    def __init__(self, leases: Iterable[Lease] = ()) -> None:
        self._leases = {lease.key: lease for lease in leases}

    def recover_expired(self, now: datetime) -> list[Lease]:
        expired = [lease for lease in self._leases.values() if lease.expired(now)]
        for lease in expired:
            self._leases.pop(lease.key, None)
        return sorted(expired, key=lambda lease: lease.key)

    def acquire(self, lease: Lease, now: datetime) -> Lease:
        if lease.acquired_at.tzinfo is None or lease.expires_at.tzinfo is None:
            raise ValueError("lease timestamps must be timezone-aware")
        if lease.expires_at <= now or lease.expires_at <= lease.acquired_at:
            raise ValueError("lease must expire in the future")
        existing = self._leases.get(lease.key)
        if existing and not existing.expired(now) and existing.owner_run_id != lease.owner_run_id:
            raise LeaseConflict(f"active lease for {lease.repository}:{lease.collision_domain}")
        generation = (existing.generation + 1) if existing else lease.generation
        acquired = replace(lease, generation=generation)
        self._leases[lease.key] = acquired
        return acquired

    def release(self, repository: str, collision_domain: str, owner_run_id: str) -> Lease:
        key = (repository, collision_domain)
        existing = self._leases.get(key)
        if existing is None or existing.owner_run_id != owner_run_id:
            raise LeaseConflict("release denied: owner mismatch or missing lease")
        return self._leases.pop(key)

    def active(self, now: datetime) -> list[Lease]:
        self.recover_expired(now)
        return sorted(self._leases.values(), key=lambda lease: lease.key)


def choose_fair_repository(repositories: list[str], last_served: str | None) -> str:
    if not repositories:
        raise ValueError("no ready repositories")
    ordered = sorted(set(repositories))
    if last_served not in ordered:
        return ordered[0]
    return ordered[(ordered.index(last_served) + 1) % len(ordered)]


def throughput_snapshot(active: Iterable[Lease], completed: dict[str, int]) -> dict[str, object]:
    leases = list(active)
    per_repository = {repo: completed.get(repo, 0) for repo in sorted(completed)}
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "active_capabilities": len(leases),
        "active_by_repository": {repo: sum(1 for lease in leases if lease.repository == repo) for repo in sorted({lease.repository for lease in leases})},
        "completed_by_repository": per_repository,
        "total_completed": sum(per_repository.values()),
    }
