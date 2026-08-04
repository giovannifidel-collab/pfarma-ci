from __future__ import annotations

import argparse
import concurrent.futures as futures
import json
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from razzo.runtime_v6.high_throughput import (
    CONFIG,
    Planner,
    ReceiptStore,
    WorkItem,
    Worker,
    load,
    percentile95,
    preflight,
    verify_one,
)


def run_cycle(mode: str, output: Path) -> dict[str, Any]:
    cfg = load(CONFIG)
    cycle = f"razzo-{uuid.uuid4().hex[:12]}"
    store = ReceiptStore(output / "receipts")
    planner = Planner(cfg)
    worker = Worker(cfg, mode, store)
    max_workers = cfg["fanout"]["hardMax"]
    max_gen = cfg["generations"]["maxPerTrigger"]
    refill = cfg["fanout"]["queueRefillThreshold"]
    verifier_workers = cfg["fanout"]["verifierMax"]
    all_receipts: list[dict[str, Any]] = []
    generations: list[dict[str, Any]] = []
    durations: list[float] = []
    speculative = 0
    logical_completed: set[str] = set()

    for generation in range(1, max_gen + 1):
        items = planner.materialize(cycle, generation)
        pending: dict[futures.Future[dict[str, Any]], WorkItem] = {}
        submitted_at: dict[futures.Future[dict[str, Any]], float] = {}
        speculated: set[str] = set()
        verified: list[dict[str, Any]] = []

        with futures.ThreadPoolExecutor(max_workers=max_workers) as pool, futures.ThreadPoolExecutor(
            max_workers=verifier_workers
        ) as verifier_pool:
            for item in items:
                future = pool.submit(worker.run, item)
                pending[future] = item
                submitted_at[future] = time.time()

            replan_marked = False
            while pending:
                done, _ = futures.wait(pending, timeout=0.05, return_when=futures.FIRST_COMPLETED)
                for future in done:
                    item = pending.pop(future)
                    submitted_at.pop(future, None)
                    receipt = future.result()
                    all_receipts.append(receipt)
                    durations.append(receipt["durationSeconds"])
                    if item.work_item_id not in logical_completed:
                        result = verifier_pool.submit(verify_one, receipt, mode).result()
                        verified.append(result)
                        if result["ok"]:
                            logical_completed.add(item.work_item_id)
                            for sibling, sibling_item in list(pending.items()):
                                if sibling_item.work_item_id == item.work_item_id:
                                    sibling.cancel()

                if len(pending) <= refill and generation < max_gen and not replan_marked:
                    generations.append(
                        {"generation": generation, "replanPreparedAtRemaining": len(pending)}
                    )
                    replan_marked = True

                threshold = percentile95(durations)
                if (
                    cfg["retry"]["strategy"] == "speculative-p95"
                    and threshold > 0
                    and len(durations) >= cfg["retry"]["minimumSamples"]
                ):
                    now = time.time()
                    for future, item in list(pending.items()):
                        if (
                            item.attempt == 1
                            and item.work_item_id not in speculated
                            and now - submitted_at[future] > threshold * 1.25
                        ):
                            retry = WorkItem(
                                **{
                                    **asdict(item),
                                    "attempt": 2,
                                    "worker_id": item.worker_id + "-spec",
                                }
                            )
                            retry_future = pool.submit(worker.run, retry)
                            pending[retry_future] = retry
                            submitted_at[retry_future] = now
                            speculated.add(item.work_item_id)
                            speculative += 1

                for future in [candidate for candidate in pending if candidate.cancelled()]:
                    pending.pop(future, None)
                    submitted_at.pop(future, None)

            if not all(result["ok"] for result in verified):
                raise RuntimeError(f"verification failed: {verified}")
            expected = {item.work_item_id for item in items}
            if len(expected & logical_completed) != len(expected):
                raise RuntimeError("one or more logical work items completed without a verified winner")

        generations.append({"generation": generation, "items": len(items), "verified": len(items)})

    events: list[tuple[float, int]] = []
    for receipt in all_receipts:
        events += [(receipt["startedEpoch"], 1), (receipt["endedEpoch"], -1)]
    active = peak = 0
    for _, delta in sorted(events, key=lambda event: (event[0], -event[1])):
        active += delta
        peak = max(peak, active)

    aggregate = {
        "cycleId": cycle,
        "mode": mode,
        "status": "green",
        "generations": max_gen,
        "logicalWorkItems": len(logical_completed),
        "attempts": len(all_receipts),
        "parallelPeak": peak,
        "targetFanout": [cfg["fanout"]["targetMin"], cfg["fanout"]["targetMax"]],
        "hardMax": max_workers,
        "queueRefillThreshold": refill,
        "incrementalReplan": cfg["generations"]["incrementalReplan"],
        "speculativeRetries": speculative,
        "receipts": len(all_receipts),
        "verified": len(logical_completed),
        "productPRs": sum(1 for receipt in all_receipts if receipt.get("prUrl")),
        "generationTelemetry": generations,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "aggregate-cycle-receipt.json").write_text(
        json.dumps(aggregate, indent=2) + "\n", encoding="utf-8"
    )
    return aggregate


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    cycle = sub.add_parser("cycle")
    cycle.add_argument("--mode", choices=["proof", "product"], default="proof")
    cycle.add_argument("--output", type=Path, required=True)
    pre = sub.add_parser("preflight")
    pre.add_argument("--mode", choices=["proof", "product"], default="proof")
    args = parser.parse_args()
    if args.command == "preflight":
        result = preflight(args.mode)
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["ok"] else 2)
    print(json.dumps(run_cycle(args.mode, args.output), indent=2))


if __name__ == "__main__":
    main()
