from datetime import datetime, timezone

import pytest

from razzo.super_factory.dispatcher import build_plan

NOW = datetime(2026, 7, 30, 8, 30, tzinfo=timezone.utc)
SHA = "a" * 40


def readiness(count=3):
    return {
        "shards": [
            {
                "shard": f"razzo-shard-{i:04d}",
                "state": "READY",
                "activation_sha": f"{i:040x}",
                "artifact_id": i,
            }
            for i in range(1, count + 1)
        ]
    }


def item(n=1, **overrides):
    value = {
        "work_item_id": f"W-{n}",
        "execution_id": f"E-{n}",
        "project_id": "pfarma",
        "generation_id": "G-1",
        "input_sha": SHA,
        "collision_domain": f"product:{n}",
        "idempotency_key": f"idem-{n}",
        "state": "QUEUED",
    }
    value.update(overrides)
    return value


def test_dispatches_only_ready_exact_sha_receipted_shards():
    snapshot = readiness(2)
    snapshot["shards"].append({"shard": "razzo-shard-0003", "state": "READY", "activation_sha": "bad", "artifact_id": 3})
    plan = build_plan(snapshot, {"items": [item()]}, {"leases": []}, now=NOW)
    assert plan["ready_count"] == 2
    assert plan["dispatch_count"] == 1
    assert plan["dispatches"][0]["repository"].startswith("giovannifidel-collab/razzo-shard-")


def test_active_lease_excludes_shard_and_idempotency_is_not_redispatched():
    leases = {
        "leases": [
            {
                "shard": "razzo-shard-0001",
                "idempotency_key": "idem-1",
                "expires_at": "2026-07-30T09:30:00Z",
            }
        ]
    }
    plan = build_plan(readiness(2), {"items": [item(1), item(2)]}, leases, now=NOW)
    assert plan["dispatch_count"] == 1
    assert plan["dispatches"][0]["shard"] == "razzo-shard-0002"
    assert plan["dispatches"][0]["inputs"]["idempotency_key"] == "idem-2"


def test_expired_lease_is_reusable():
    leases = {"leases": [{"shard": "razzo-shard-0001", "expires_at": "2026-07-30T07:00:00Z"}]}
    plan = build_plan(readiness(1), {"items": [item()]}, leases, now=NOW)
    assert plan["dispatch_count"] == 1


def test_invalid_input_sha_fails_closed():
    with pytest.raises(ValueError, match="input_sha"):
        build_plan(readiness(1), {"items": [item(input_sha="main")]}, {"leases": []}, now=NOW)


def test_limit_and_one_work_item_per_shard():
    plan = build_plan(readiness(3), {"items": [item(1), item(2), item(3)]}, {"leases": []}, now=NOW, limit=2)
    assert plan["dispatch_count"] == 2
    assert len({d["shard"] for d in plan["dispatches"]}) == 2
