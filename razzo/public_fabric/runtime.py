from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "razzo/public_fabric/config.json"
PROJECTS = ROOT / "razzo/projects.json"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stable(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


@dataclass(frozen=True)
class Lease:
    cycleId: str
    generation: int
    workItemId: str
    shard: str
    projectId: str
    repository: str
    targetLane: str
    exactInputSha: str
    verticalSlice: str
    collisionDomain: str
    idempotencyKey: str
    attempt: int


class FabricPlanner:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def enabled_projects(self) -> list[dict[str, Any]]:
        return [p for p in load(PROJECTS).get("projects", []) if p.get("enabled", True)]

    def materialize(self, cycle_id: str, generation: int, exact_refs: dict[str, str]) -> list[Lease]:
        projects = self.enabled_projects()
        shards = self.config["shards"][: self.config["targetFanout"]["max"]]
        target = min(len(shards), self.config["targetFanout"]["max"])
        if target < self.config["targetFanout"]["min"]:
            raise RuntimeError("insufficient configured public shards")
        counts = {p["id"]: 0 for p in projects}
        leases: list[Lease] = []
        cursor = 0
        slices = ("discovery", "product-slice", "robot-journey", "repair", "contract", "integration-readiness")
        while len(leases) < target:
            project = projects[cursor % len(projects)]
            if counts[project["id"]] >= self.config["buildersPerRepository"]["max"]:
                cursor += 1
                continue
            vertical = f"{slices[counts[project['id']] % len(slices)]}-g{generation}-{counts[project['id']]}"
            collision = f"{project['id']}:{vertical.split('-g')[0]}"
            exact_sha = exact_refs[project["id"]]
            item_id = stable(cycle_id, str(generation), project["id"], vertical)
            leases.append(
                Lease(
                    cycleId=cycle_id,
                    generation=generation,
                    workItemId=item_id,
                    shard=shards[len(leases)],
                    projectId=project["id"],
                    repository=project["repository"],
                    targetLane=project.get("integrationLane", "main"),
                    exactInputSha=exact_sha,
                    verticalSlice=vertical,
                    collisionDomain=collision,
                    idempotencyKey=stable(project["id"], vertical, exact_sha),
                    attempt=1,
                )
            )
            counts[project["id"]] += 1
            cursor += 1
        return leases


class GitHubAPI:
    def __init__(self, token: str):
        self.token = token

    def request(self, method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                body = response.read().decode()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"GitHub API {exc.code}: {exc.read().decode()}") from exc

    def actions_permissions(self, owner: str, shard: str) -> dict[str, Any]:
        return self.request("GET", f"https://api.github.com/repos/{owner}/{shard}/actions/permissions")

    def dispatch(self, owner: str, shard: str, event: str, lease: Lease) -> None:
        envelope = {
            "schema": "razzo.work-item-envelope.v1",
            "workItemId": lease.workItemId,
            "lease": asdict(lease),
        }
        self.request(
            "POST",
            f"https://api.github.com/repos/{owner}/{shard}/dispatches",
            {"event_type": event, "client_payload": envelope},
        )


class ReceiptVerifier:
    REQUIRED = {"cycleId", "generation", "workItemId", "shard", "status", "startedEpoch", "endedEpoch"}

    def verify(self, receipt: dict[str, Any], lease: Lease) -> dict[str, Any]:
        missing = sorted(self.REQUIRED - set(receipt))
        if missing:
            return {"ok": False, "error": f"missing fields: {missing}"}
        if receipt["workItemId"] != lease.workItemId or receipt["shard"] != lease.shard:
            return {"ok": False, "error": "lease identity mismatch"}
        if receipt["status"] != "completed":
            return {"ok": False, "error": receipt.get("error", "shard failed")}
        if receipt.get("exactInputSha") != lease.exactInputSha:
            return {"ok": False, "error": "exact SHA mismatch"}
        return {"ok": True, "workItemId": lease.workItemId}


def p95(values: list[float]) -> float:
    if len(values) < 2:
        return max(values or [0.0])
    return statistics.quantiles(values, n=20, method="inclusive")[18]


def proof(output: Path) -> dict[str, Any]:
    cfg = load(CONFIG)
    projects = [p for p in load(PROJECTS).get("projects", []) if p.get("enabled", True)]
    refs = {p["id"]: "a" * 40 for p in projects}
    planner = FabricPlanner(cfg)
    cycle = f"razzo-{uuid.uuid4().hex[:12]}"
    all_leases: list[Lease] = []
    telemetry: list[dict[str, Any]] = []
    for generation in range(1, cfg["maxGenerationsPerTrigger"] + 1):
        leases = planner.materialize(cycle, generation, refs)
        all_leases.extend(leases)
        telemetry.append(
            {
                "generation": generation,
                "leases": len(leases),
                "replanPreparedAtRemaining": cfg["queueRefillThreshold"]
                if generation < cfg["maxGenerationsPerTrigger"]
                else 0,
            }
        )
    aggregate = {
        "cycleId": cycle,
        "status": "green",
        "mode": "PUBLIC_FABRIC_PROOF",
        "configuredShards": len(cfg["shards"]),
        "generations": cfg["maxGenerationsPerTrigger"],
        "logicalWorkItems": len(all_leases),
        "targetFanout": cfg["targetFanout"],
        "queueRefillThreshold": cfg["queueRefillThreshold"],
        "incrementalReplan": cfg["incrementalReplan"],
        "speculativeRetry": cfg["speculativeRetry"],
        "receiptPerJob": cfg["receiptPerJob"],
        "aggregateReceipt": cfg["aggregateReceipt"],
        "oneProductPrPerVerticalSlice": cfg["oneProductPrPerVerticalSlice"],
        "generationTelemetry": telemetry,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "leases.json").write_text(json.dumps([asdict(x) for x in all_leases], indent=2) + "\n")
    (output / "aggregate-cycle-receipt.json").write_text(json.dumps(aggregate, indent=2) + "\n")
    return aggregate


def dispatch(output: Path, exact_refs_path: Path) -> dict[str, Any]:
    cfg = load(CONFIG)
    token = os.environ.get(cfg["tokenSecret"])
    if not token:
        raise RuntimeError(f"missing {cfg['tokenSecret']}")
    refs = load(exact_refs_path)
    planner = FabricPlanner(cfg)
    api = GitHubAPI(token)
    cycle = f"razzo-{uuid.uuid4().hex[:12]}"
    leases = planner.materialize(cycle, 1, refs)

    output.mkdir(parents=True, exist_ok=True)
    (output / "planned-leases.json").write_text(json.dumps([asdict(x) for x in leases], indent=2) + "\n")

    permission_rows: list[dict[str, Any]] = []
    for shard in dict.fromkeys(lease.shard for lease in leases):
        row: dict[str, Any] = {"shard": shard}
        try:
            permission = api.actions_permissions(cfg["owner"], shard)
            row.update(
                {
                    "enabled": permission.get("enabled"),
                    "allowed_actions": permission.get("allowed_actions"),
                    "selected_actions_url": permission.get("selected_actions_url"),
                }
            )
        except Exception as exc:
            row["error"] = str(exc)
        permission_rows.append(row)
    (output / "actions-permissions.json").write_text(json.dumps(permission_rows, indent=2) + "\n")

    dispatched: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for lease in leases:
        try:
            api.dispatch(cfg["owner"], lease.shard, cfg["dispatchEvent"], lease)
            dispatched.append(asdict(lease))
        except Exception as exc:
            failures.append({"workItemId": lease.workItemId, "shard": lease.shard, "error": str(exc)})

    (output / "dispatched-leases.json").write_text(json.dumps(dispatched, indent=2) + "\n")
    (output / "dispatch-failures.json").write_text(json.dumps(failures, indent=2) + "\n")
    if failures:
        raise RuntimeError(f"{len(failures)} of {len(leases)} shard dispatches failed")
    return {
        "cycleId": cycle,
        "status": "dispatched",
        "leases": len(dispatched),
        "actionsEnabled": sum(1 for row in permission_rows if row.get("enabled") is True),
        "actionsChecked": len(permission_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("proof")
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("dispatch")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--exact-refs", type=Path, required=True)
    args = parser.parse_args()
    result = proof(args.output) if args.command == "proof" else dispatch(args.output, args.exact_refs)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
