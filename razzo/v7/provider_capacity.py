from __future__ import annotations

from dataclasses import dataclass, asdict
from statistics import median
from typing import Any, Iterable


@dataclass(frozen=True)
class ProviderObservation:
    observed_peak: int
    queue_wait_seconds: float
    throughput_per_minute: float
    prior_throughput_per_minute: float
    queued_runs: int = 0
    in_progress_runs: int = 0


@dataclass(frozen=True)
class ProviderCapacityDecision:
    operational_cap: int
    action: str
    reason: str
    throughput_gain: float
    queue_wait_seconds: float
    observed_peak: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def derive_operational_cap(
    observation: ProviderObservation,
    *,
    normal_concurrency: int,
    registry_burst: int,
    previous_cap: int,
) -> ProviderCapacityDecision:
    """Derive a bounded provider-aware cap from measured execution telemetry.

    The registry burst remains the hard logical ceiling. The operational cap is
    allowed to grow only when measured throughput improves without material
    queueing. High queue wait or a growing queued-run backlog causes scale-down.
    """
    normal = max(1, normal_concurrency)
    burst = max(normal, registry_burst)
    previous = max(normal, min(previous_cap, burst))
    peak = max(1, min(observation.observed_peak, burst))
    current_tp = max(0.0, observation.throughput_per_minute)
    prior_tp = max(0.0, observation.prior_throughput_per_minute)
    gain = 1.0 if prior_tp == 0 and current_tp > 0 else (
        0.0 if prior_tp == 0 else (current_tp - prior_tp) / prior_tp
    )
    wait = max(0.0, observation.queue_wait_seconds)

    provider_pressure = observation.queued_runs > max(2, observation.in_progress_runs)
    if wait >= 120 or provider_pressure:
        cap = max(normal, min(previous, peak))
        if cap >= previous:
            cap = max(normal, int(previous * 0.75))
        return ProviderCapacityDecision(
            cap, "scale_down", "provider-queue-pressure", gain, wait, peak
        )

    if gain >= 0.05 and wait <= 60:
        growth = max(1, previous // 2)
        cap = min(burst, max(previous + growth, peak))
        action = "scale_up" if cap > previous else "hold"
        reason = "measured-throughput-gain" if action == "scale_up" else "registry-burst-cap"
        return ProviderCapacityDecision(cap, action, reason, gain, wait, peak)

    if gain < -0.05:
        cap = max(normal, min(peak, int(previous * 0.8)))
        return ProviderCapacityDecision(
            cap, "scale_down", "throughput-regression", gain, wait, peak
        )

    cap = max(normal, min(previous, max(peak, normal)))
    return ProviderCapacityDecision(cap, "hold", "stable-provider-capacity", gain, wait, peak)


def observed_peak(intervals: Iterable[tuple[float, float]]) -> int:
    """Return measured maximum overlap for [start,end) worker intervals."""
    events: list[tuple[float, int]] = []
    for start, end in intervals:
        if end <= start:
            continue
        events.append((start, 1))
        events.append((end, -1))
    current = peak = 0
    for _, delta in sorted(events, key=lambda item: (item[0], item[1])):
        current += delta
        peak = max(peak, current)
    return peak


def median_queue_wait(values: Iterable[float]) -> float:
    cleaned = [max(0.0, float(v)) for v in values]
    return float(median(cleaned)) if cleaned else 0.0
