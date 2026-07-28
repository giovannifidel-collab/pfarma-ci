from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from razzo.v7.autoscaler import ScaleDecision, ScaleInput, decide


@dataclass(frozen=True)
class FabricPlan:
    provider: str
    desired_concurrency: int
    materialized_workers: int
    provider_cap: int
    burst_cap: int
    action: str
    reason: str
    worker_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_plan(inp: ScaleInput, provider_cap: int, provider: str = "github-actions") -> FabricPlan:
    """Translate an autoscaler decision into a bounded concrete worker plan.

    The provider cap is a second hard safety ceiling below the registry burst cap.
    This makes the first V7 fabric deployable without interpreting elastic as infinite.
    """
    decision: ScaleDecision = decide(inp)
    cap = max(1, min(provider_cap, inp.burst_concurrency))
    materialized = max(1, min(decision.desired_concurrency, cap))
    worker_ids = [f"v7-worker-{i:03d}" for i in range(1, materialized + 1)]
    return FabricPlan(
        provider=provider,
        desired_concurrency=decision.desired_concurrency,
        materialized_workers=materialized,
        provider_cap=cap,
        burst_cap=inp.burst_concurrency,
        action=decision.action,
        reason=decision.reason,
        worker_ids=worker_ids,
    )


def receipt(worker_id: str, exact_sha: str, work_item_id: str) -> dict[str, str]:
    payload = f"{worker_id}:{exact_sha}:{work_item_id}".encode()
    return {
        "worker_id": worker_id,
        "exact_sha": exact_sha,
        "work_item_id": work_item_id,
        "receipt_digest": hashlib.sha256(payload).hexdigest(),
        "status": "verified",
    }


def matrix_json(plan: FabricPlan) -> str:
    return json.dumps({"worker": plan.worker_ids}, separators=(",", ":"))
