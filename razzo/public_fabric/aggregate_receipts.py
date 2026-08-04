from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from collections import Counter
from dataclasses import fields
from pathlib import Path
from typing import Any

from razzo.public_fabric.runtime import Lease, ReceiptVerifier, p95

MARKER_PREFIX = "<!-- RAZZO_RECEIPT_JSON "
MARKER_SUFFIX = " -->"


def request(method: str, url: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=45) as response:
        raw = response.read().decode()
        return json.loads(raw) if raw else {}


def fetch_recent_comment_bodies(repository: str, issue_number: int, token: str) -> list[str]:
    owner, name = repository.split("/", 1)
    query = """
    query($owner:String!, $name:String!, $number:Int!) {
      repository(owner:$owner, name:$name) {
        issue(number:$number) {
          comments(last:100) { nodes { body } }
        }
      }
    }
    """
    payload = {
        "query": query,
        "variables": {"owner": owner, "name": name, "number": issue_number},
    }
    result = request("POST", "https://api.github.com/graphql", token, payload)
    nodes = result["data"]["repository"]["issue"]["comments"]["nodes"]
    return [str(node.get("body", "")) for node in nodes]


def extract_receipts(bodies: list[str], cycle_id: str) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for body in bodies:
        start = body.find(MARKER_PREFIX)
        if start < 0:
            continue
        start += len(MARKER_PREFIX)
        end = body.find(MARKER_SUFFIX, start)
        if end < 0:
            continue
        try:
            receipt = json.loads(body[start:end])
        except json.JSONDecodeError:
            continue
        if receipt.get("cycleId") == cycle_id:
            receipts.append(receipt)
    return receipts


def parallel_peak(receipts: list[dict[str, Any]]) -> int:
    events: list[tuple[float, int]] = []
    for receipt in receipts:
        events.append((float(receipt["startedEpoch"]), 1))
        events.append((float(receipt["endedEpoch"]), -1))
    active = 0
    peak = 0
    for _, delta in sorted(events, key=lambda item: (item[0], item[1])):
        active += delta
        peak = max(peak, active)
    return peak


def compact_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "cycleId",
        "generation",
        "generationId",
        "workItemId",
        "shard",
        "projectId",
        "repository",
        "targetLane",
        "title",
        "kind",
        "priority",
        "collisionDomain",
        "verification",
        "idempotencyKey",
        "attempt",
        "startedEpoch",
        "endedEpoch",
        "durationSeconds",
        "status",
        "exactInputSha",
        "observedSha",
        "commands",
        "metrics",
        "error",
    }
    return {key: receipt[key] for key in receipt if key in allowed}


def aggregate(leases: list[dict[str, Any]], receipts: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    lease_fields = {field.name for field in fields(Lease)}
    expected = {
        lease["workItemId"]: Lease(**{key: lease[key] for key in lease_fields})
        for lease in leases
    }
    counts = Counter(receipt.get("workItemId") for receipt in receipts)
    duplicates = sorted(item for item, count in counts.items() if item and count > 1)
    receipt_ids = {receipt.get("workItemId") for receipt in receipts if receipt.get("workItemId")}
    by_id = {receipt["workItemId"]: receipt for receipt in receipts if receipt.get("workItemId") in expected}
    missing = sorted(set(expected) - set(by_id))
    unexpected = sorted(receipt_ids - set(expected))

    verifier = ReceiptVerifier()
    checks = []
    for work_item_id, lease in expected.items():
        receipt = by_id.get(work_item_id)
        if receipt is None:
            checks.append({"ok": False, "workItemId": work_item_id, "error": "missing receipt"})
        else:
            checks.append(verifier.verify(receipt, lease))

    verified = sum(1 for check in checks if check.get("ok"))
    failed = [check for check in checks if not check.get("ok")]
    completed_receipts = [receipt for receipt in by_id.values() if receipt.get("status") == "completed"]
    durations = [float(receipt.get("durationSeconds", 0)) for receipt in completed_receipts]
    commands_executed = sum(len(receipt.get("commands") or []) for receipt in completed_receipts)
    discovery = [receipt for receipt in completed_receipts if receipt.get("kind") == "discovery"]
    markers = sum(
        int((receipt.get("metrics") or {}).get(key, 0))
        for receipt in discovery
        for key in ("todoMarkerCount", "fixmeMarkerCount", "placeholderMarkerCount", "mockMarkerCount")
    )
    starts = [float(receipt["startedEpoch"]) for receipt in completed_receipts]
    ends = [float(receipt["endedEpoch"]) for receipt in completed_receipts]
    status = "green" if not missing and not unexpected and not duplicates and not failed else "red"
    project_counts = Counter(receipt.get("projectId") for receipt in completed_receipts)
    kinds = Counter(receipt.get("kind") for receipt in completed_receipts)
    product_integrations = sum(1 for receipt in completed_receipts if receipt.get("kind") == "product-integration")

    aggregate_receipt = {
        "schema": "razzo.aggregate-cycle-receipt.v1",
        "cycleId": leases[0]["cycleId"],
        "generationId": leases[0]["generationId"],
        "mode": "OPERATIONAL_PROOF" if product_integrations == 0 else "PRODUCT_PROGRESS",
        "status": status,
        "portfolioSize": len({lease["projectId"] for lease in leases}),
        "projectsScanned": sorted({lease["projectId"] for lease in leases}),
        "workstreamsEligible": len(leases),
        "workstreamsDispatched": len(leases),
        "workstreamsCompleted": len(completed_receipts),
        "workstreamsFailed": len(failed),
        "workstreamsRetried": sum(max(0, int(receipt.get("attempt", 1)) - 1) for receipt in receipts),
        "workstreamsVerified": verified,
        "workstreamsIntegrated": product_integrations,
        "duplicateExecutions": duplicates,
        "missingReceipts": missing,
        "unexpectedReceipts": unexpected,
        "testsExecuted": commands_executed,
        "discoveryScans": len(discovery),
        "sanitizedMarkersObserved": markers,
        "parallelPeak": parallel_peak(completed_receipts) if completed_receipts else 0,
        "utilizationRate": round(len(completed_receipts) / len(leases), 4) if leases else 0,
        "cycleDurationSeconds": round(max(ends) - min(starts), 3) if starts and ends else 0,
        "workerDurationP50Seconds": round(statistics_median(durations), 3),
        "workerDurationP95Seconds": round(p95(durations), 3),
        "projectCompletionCounts": dict(sorted(project_counts.items())),
        "kindCompletionCounts": dict(sorted(kinds.items())),
        "exactShaGates": verified,
        "humanGatesEncountered": 0,
        "productProgress": product_integrations > 0,
        "generationPromoted": product_integrations > 0 and status == "green",
        "safeWorkRemaining": True,
        "startEpoch": min(starts) if starts else None,
        "endEpoch": max(ends) if ends else None,
    }
    verification = {
        "schema": "razzo.receipt-verification.v1",
        "cycleId": aggregate_receipt["cycleId"],
        "status": status,
        "checks": checks,
    }
    return aggregate_receipt, verification


def statistics_median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def post_summary(repository: str, issue_number: int, token: str, aggregate_receipt: dict[str, Any]) -> None:
    body = (
        "`PUBLIC_FABRIC_CYCLE_VERIFIED`\n\n"
        f"- cycle ID: `{aggregate_receipt['cycleId']}`;\n"
        f"- generation ID: `{aggregate_receipt['generationId']}`;\n"
        f"- status: `{aggregate_receipt['status']}`;\n"
        f"- mode: `{aggregate_receipt['mode']}`;\n"
        f"- dispatched/completed/verified: `{aggregate_receipt['workstreamsDispatched']}/"
        f"{aggregate_receipt['workstreamsCompleted']}/{aggregate_receipt['workstreamsVerified']}`;\n"
        f"- parallel peak: `{aggregate_receipt['parallelPeak']}`;\n"
        f"- utilization: `{aggregate_receipt['utilizationRate']}`;\n"
        f"- tests executed: `{aggregate_receipt['testsExecuted']}`;\n"
        f"- discovery scans: `{aggregate_receipt['discoveryScans']}`;\n"
        f"- duplicate executions: `{len(aggregate_receipt['duplicateExecutions'])}`;\n"
        f"- exact-SHA gates: `{aggregate_receipt['exactShaGates']}`;\n"
        f"- product progress: `{str(aggregate_receipt['productProgress']).lower()}`;\n"
        f"- generation promoted: `{str(aggregate_receipt['generationPromoted']).lower()}`.\n"
        f"<!-- RAZZO_AGGREGATE_JSON {json.dumps(aggregate_receipt, separators=(',', ':'))} -->"
    )
    request(
        "POST",
        f"https://api.github.com/repos/{repository}/issues/{issue_number}/comments",
        token,
        {"body": body},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repository:
        raise SystemExit("GH_TOKEN and GITHUB_REPOSITORY are required")
    leases = json.loads(args.leases.read_text(encoding="utf-8"))
    cycle_id = leases[0]["cycleId"]
    expected_ids = {lease["workItemId"] for lease in leases}
    deadline = time.time() + args.timeout
    receipts: list[dict[str, Any]] = []
    while time.time() < deadline:
        receipts = extract_receipts(fetch_recent_comment_bodies(repository, args.issue, token), cycle_id)
        observed_ids = {receipt.get("workItemId") for receipt in receipts}
        if expected_ids.issubset(observed_ids):
            break
        time.sleep(5)

    aggregate_receipt, verification = aggregate(leases, receipts)
    args.output.mkdir(parents=True, exist_ok=True)
    compact = [compact_receipt(receipt) for receipt in receipts]
    (args.output / "receipt-set.json").write_text(json.dumps(compact, indent=2) + "\n", encoding="utf-8")
    (args.output / "verification-summary.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    (args.output / "aggregate-cycle-receipt.json").write_text(
        json.dumps(aggregate_receipt, indent=2) + "\n", encoding="utf-8"
    )
    queue_final = {
        "schema": "razzo.public-queue-final.v1",
        "cycleId": cycle_id,
        "status": "verified" if aggregate_receipt["status"] == "green" else "failed",
        "workItems": compact,
    }
    (args.output / "queue-final.json").write_text(json.dumps(queue_final, indent=2) + "\n", encoding="utf-8")
    post_summary(repository, args.issue, token, aggregate_receipt)
    print(json.dumps(aggregate_receipt, indent=2))
    return 0 if aggregate_receipt["status"] == "green" else 2


if __name__ == "__main__":
    raise SystemExit(main())
