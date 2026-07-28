from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
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
    """Derive a bounded provider-aware cap from measured execution telemetry."""
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


def _parse_time(value: str | None) -> float | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def _github_json(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "razzo-provider-capacity",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def _all_jobs(repo: str, run_id: int, token: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = _github_json(
            f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100&page={page}",
            token,
        )
        chunk = payload.get("jobs", [])
        jobs.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
    return jobs


def collect_observation(repo: str, workflow: str, token: str) -> ProviderObservation:
    workflow_id = urllib.parse.quote(workflow, safe="")
    payload = _github_json(
        f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_id}/runs?per_page=20",
        token,
    )
    runs = payload.get("workflow_runs", [])
    queued_runs = sum(1 for run in runs if run.get("status") == "queued")
    in_progress_runs = sum(1 for run in runs if run.get("status") == "in_progress")
    completed_runs = [run for run in runs if run.get("status") == "completed" and run.get("conclusion") == "success"][:2]

    throughputs: list[float] = []
    peaks: list[int] = []
    waits: list[float] = []
    for run in completed_runs:
        created = _parse_time(run.get("created_at"))
        jobs = _all_jobs(repo, int(run["id"]), token)
        worker_jobs = [job for job in jobs if str(job.get("name", "")).startswith("workers")]
        intervals: list[tuple[float, float]] = []
        for job in worker_jobs:
            started = _parse_time(job.get("started_at"))
            completed = _parse_time(job.get("completed_at"))
            if started is not None and completed is not None and completed > started:
                intervals.append((started, completed))
                if created is not None:
                    waits.append(max(0.0, started - created))
        if intervals:
            peaks.append(observed_peak(intervals))
            start = min(item[0] for item in intervals)
            end = max(item[1] for item in intervals)
            minutes = max((end - start) / 60.0, 1 / 60.0)
            throughputs.append(len(intervals) / minutes)

    return ProviderObservation(
        observed_peak=max(peaks, default=1),
        queue_wait_seconds=median_queue_wait(waits),
        throughput_per_minute=throughputs[0] if throughputs else 0.0,
        prior_throughput_per_minute=throughputs[1] if len(throughputs) > 1 else 0.0,
        queued_runs=queued_runs,
        in_progress_runs=in_progress_runs,
    )


def _registry_limits(path: str) -> tuple[int, int]:
    payload = json.loads(open(path, encoding="utf-8").read())
    return int(payload.get("totalNormalSlots", 1)), int(payload.get("totalBurstSlots", 1))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default="razzo/projects.json")
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--workflow", default="razzo-v7-product-worker-fabric.yml")
    parser.add_argument("--previous-cap", type=int, default=220)
    parser.add_argument("--cap-only", action="store_true")
    args = parser.parse_args()

    normal, burst = _registry_limits(args.registry)
    token = os.getenv("GITHUB_TOKEN", "")
    if not args.repo or not token:
        decision = ProviderCapacityDecision(
            operational_cap=max(normal, min(args.previous_cap, burst)),
            action="hold",
            reason="telemetry-unavailable",
            throughput_gain=0.0,
            queue_wait_seconds=0.0,
            observed_peak=1,
        )
    else:
        try:
            observation = collect_observation(args.repo, args.workflow, token)
            decision = derive_operational_cap(
                observation,
                normal_concurrency=normal,
                registry_burst=burst,
                previous_cap=args.previous_cap,
            )
        except Exception as exc:
            decision = ProviderCapacityDecision(
                operational_cap=max(normal, min(args.previous_cap, burst)),
                action="hold",
                reason=f"telemetry-error:{type(exc).__name__}",
                throughput_gain=0.0,
                queue_wait_seconds=0.0,
                observed_peak=1,
            )

    if args.cap_only:
        print(decision.operational_cap)
    else:
        print(json.dumps(decision.to_dict(), sort_keys=True))


if __name__ == "__main__":
    main()
