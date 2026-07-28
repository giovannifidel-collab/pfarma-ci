from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class ScaleInput:
    queued: int
    running: int
    completed: int
    failed: int
    current_concurrency: int
    normal_concurrency: int
    burst_concurrency: int
    backpressure: bool = False
    human_gate_only: bool = False
    provider_cap: int | None = None


@dataclass(frozen=True)
class ScaleDecision:
    desired_concurrency: int
    action: str
    reason: str
    utilization_pressure: float
    failure_rate: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide(inp: ScaleInput) -> ScaleDecision:
    """Return a deterministic, bounded autoscaling decision.

    V7 never interprets 'elastic' as unbounded. The registry burst limit is a
    hard logical ceiling. When measured provider capacity is available it is a
    second, lower operational ceiling. Backpressure and elevated failure rate
    force scale-down. Human-gate-only queues do not consume workers.
    """
    current = max(1, inp.current_concurrency)
    normal = max(1, inp.normal_concurrency)
    registry_burst = max(normal, inp.burst_concurrency)
    provider_cap = registry_burst if inp.provider_cap is None else max(normal, inp.provider_cap)
    burst = min(registry_burst, provider_cap)
    queued = max(0, inp.queued)
    running = max(0, inp.running)
    attempts = max(1, inp.completed + inp.failed)
    failure_rate = inp.failed / attempts
    pressure = queued / max(1, current)

    if inp.human_gate_only:
        return ScaleDecision(1, "scale_down", "human-gate-only queue", pressure, failure_rate)

    if inp.backpressure or failure_rate >= 0.20:
        desired = max(1, min(normal, current // 2 or 1))
        return ScaleDecision(desired, "scale_down", "backpressure-or-failure-rate", pressure, failure_rate)

    if queued == 0 and running == 0:
        return ScaleDecision(1, "scale_down", "idle", pressure, failure_rate)

    if current > burst:
        return ScaleDecision(burst, "scale_down", "provider-cap", pressure, failure_rate)

    if queued > current * 2:
        desired = min(burst, max(normal, current * 2))
        action = "scale_up" if desired > current else "hold"
        reason = "queue-pressure" if action == "scale_up" else "operational-cap"
        return ScaleDecision(desired, action, reason, pressure, failure_rate)

    if queued > current:
        desired = min(burst, max(normal, current + max(1, current // 2)))
        action = "scale_up" if desired > current else "hold"
        reason = "moderate-queue-pressure" if action == "scale_up" else "operational-cap"
        return ScaleDecision(desired, action, reason, pressure, failure_rate)

    floor = min(normal, max(1, queued + running))
    desired = max(1, min(current, floor, burst))
    action = "scale_down" if desired < current else "hold"
    return ScaleDecision(desired, action, "balanced", pressure, failure_rate)


def geometric_ramp(start: int, burst: int, waves: int) -> list[int]:
    """Operational-proof helper: bounded doubling sequence, never beyond burst."""
    value = max(1, start)
    cap = max(value, burst)
    out = [value]
    for _ in range(max(0, waves - 1)):
        value = min(cap, value * 2)
        out.append(value)
    return out
