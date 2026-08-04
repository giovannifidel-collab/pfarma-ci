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
    """Fail-closed lease table with exactly one active capability per repository.

    The collision domain remains part of the canonical identity and release contract,
    but a repository owns only one product slot at a time. This permits three-way
    parallelism across the three product repositories without admitting two
    capabilities that can still interfere through shared repository state.
    """

    def __init__(self, leases: Iterable[Lease] = ()) -> None:
        self._leases: dict[tuple[str, str], Lease] = {}
        for lease in leases:
            if lease.key in self._leases:
                raise LeaseConflict(f"duplicate lease key for {lease.repository}:{lease.collision_domain}")
            if any(active.repository == lease.repository for active in self._leases.values()):
                raise LeaseConflict(f"multiple active capabilities for repository {lease.repository}")
            self._leases[lease.key] = lease

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

        self.recover_expired(now)
        same_key = self._leases.get(lease.key)
        repository_lease = next(
            (active for active in self._leases.values() if active.repository == lease.repository),
            None,
        )
        if repository_lease is not None and repository_lease.owner_run_id != lease.owner_run_id:
            raise LeaseConflict(
                f"repository slot occupied by {repository_lease.collision_domain} for {lease.repository}"
            )
        if repository_lease is not None and repository_lease.key != lease.key:
            raise LeaseConflict(
                f"owner cannot switch collision domain while repository slot is active: {lease.repository}"
            )

        generation = (same_key.generation + 1) if same_key else lease.generation
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
        active = sorted(self._leases.values(), key=lambda lease: lease.key)
        repositories = [lease.repository for lease in active]
        if len(repositories) != len(set(repositories)):
            raise LeaseConflict("runtime contains multiple active capabilities for one repository")
        return active


def choose_fair_repository(repositories: list[str], last_served: str | None) -> str:
    if not repositories:
        raise ValueError("no ready repositories")
    ordered = sorted(set(repositories))
    if last_served not in ordered:
        return ordered[0]
    return ordered[(ordered.index(last_served) + 1) % len(ordered)]


def throughput_snapshot(active: Iterable[Lease], completed: dict[str, int]) -> dict[str, object]:
    leases = list(active)
    repositories = [lease.repository for lease in leases]
    if len(repositories) != len(set(repositories)):
        raise LeaseConflict("throughput snapshot rejects multiple active capabilities per repository")
    per_repository = {repo: completed.get(repo, 0) for repo in sorted(completed)}
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "active_capabilities": len(leases),
        "active_by_repository": {repo: 1 for repo in sorted(repositories)},
        "completed_by_repository": per_repository,
        "total_completed": sum(per_repository.values()),
    }
