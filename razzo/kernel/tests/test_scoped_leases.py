from datetime import datetime, timedelta, timezone

import pytest

from razzo.kernel.scoped_leases import Lease, LeaseConflict, ScopedLeaseTable, choose_fair_repository, throughput_snapshot

NOW = datetime(2026, 8, 4, 0, 36, tzinfo=timezone.utc)


def lease(repo: str, domain: str, owner: str = "run-1", minutes: int = 30) -> Lease:
    return Lease(repo, domain, owner, NOW, NOW + timedelta(minutes=minutes))


def test_independent_repositories_run_in_parallel():
    table = ScopedLeaseTable()
    table.acquire(lease("project-giovanni", "profile"), NOW)
    table.acquire(lease("pfarma-cloud", "recall"), NOW)
    table.acquire(lease("family-cloud", "library"), NOW)
    assert len(table.active(NOW)) == 3


def test_same_repository_and_domain_is_fail_closed():
    table = ScopedLeaseTable([lease("pfarma-cloud", "recall", "run-a")])
    with pytest.raises(LeaseConflict):
        table.acquire(lease("pfarma-cloud", "recall", "run-b"), NOW)


def test_expired_lease_is_recovered_before_acquire():
    expired = Lease("family-cloud", "library", "old", NOW - timedelta(hours=2), NOW - timedelta(hours=1))
    table = ScopedLeaseTable([expired])
    assert table.recover_expired(NOW) == [expired]
    assert table.acquire(lease("family-cloud", "library", "new"), NOW).owner_run_id == "new"


def test_release_requires_exact_owner():
    table = ScopedLeaseTable([lease("project-giovanni", "profile", "owner")])
    with pytest.raises(LeaseConflict):
        table.release("project-giovanni", "profile", "other")


def test_round_robin_fairness_is_deterministic():
    repos = ["pfarma-cloud", "family-cloud", "project-giovanni"]
    assert choose_fair_repository(repos, None) == "family-cloud"
    assert choose_fair_repository(repos, "family-cloud") == "pfarma-cloud"
    assert choose_fair_repository(repos, "project-giovanni") == "family-cloud"


def test_throughput_snapshot_counts_active_and_completed():
    active = [lease("pfarma-cloud", "recall"), lease("family-cloud", "library")]
    snapshot = throughput_snapshot(active, {"pfarma-cloud": 3, "family-cloud": 2})
    assert snapshot["active_capabilities"] == 2
    assert snapshot["total_completed"] == 5
    assert snapshot["active_by_repository"] == {"family-cloud": 1, "pfarma-cloud": 1}
