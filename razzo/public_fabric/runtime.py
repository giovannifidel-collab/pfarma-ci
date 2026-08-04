from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import time
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
    generationId: str
    workItemId: str
    shard: str
    projectId: str
    repository: str
    targetLane: str
    exactInputSha: str
    title: str
    kind: str
    priority: str
    dependencies: tuple[str, ...]
    verticalSlice: str
    collisionDomain: str
    verification: str
    humanGate: str | None
    idempotencyKey: str
    status: str
    leasedEpoch: float
    leaseExpiresEpoch: float
    attempt: int
    maxAttempts: int
    commands: tuple[str, ...]


class FabricPlanner:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def enabled_projects(self) -> list[dict[str, Any]]:
        return [p for p in load(PROJECTS).get("projects", []) if p.get("enabled", True)]

    @staticmethod
    def workstreams(project: dict[str, Any]) -> list[dict[str, Any]]:
        configured = project.get("publicFabricWorkstreams")
        if configured:
            return configured
        fallback = []
        if project.get("factoryTest"):
            fallback.append(
                {
                    "id": "factory-tests",
                    "title": "Factory regression suite",
                    "kind": "verification",
                    "priority": "P0",
                    "command": project["factoryTest"],
                    "verification": "exit-zero+exact-sha",
                }
            )
        if project.get("factoryPlan"):
            fallback.append(
                {
                    "id": "factory-plan",
                    "title": "Factory planner execution",
                    "kind": "planning",
                    "priority": "P1",
                    "command": project["factoryPlan"],
                    "verification": "exit-zero+exact-sha",
                }
            )
        fallback.extend(
            [
                {
                    "id": "repository-integrity",
                    "title": "Repository object integrity",
                    "kind": "integrity",
                    "priority": "P1",
                    "command": "git fsck --no-dangling",
                    "verification": "exit-zero+exact-sha",
                },
                {
                    "id": "product-discovery",
                    "title": "Sanitized product discovery scan",
                    "kind": "discovery",
                    "priority": "P1",
                    "verification": "sanitized-metrics+exact-sha",
                },
            ]
        )
        return fallback

    def materialize(self, cycle_id: str, generation: int, exact_refs: dict[str, str]) -> list[Lease]:
        projects = self.enabled_projects()
        if not projects:
            raise RuntimeError("no enabled projects")
        shards = self.config["shards"][: self.config["targetFanout"]["max"]]
        target = min(len(shards), self.config["targetFanout"]["max"])
        if target < self.config["targetFanout"]["min"]:
            raise RuntimeError("insufficient configured public shards")

        candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
        per_project = max(1, self.config["buildersPerRepository"]["min"])
        for project in projects:
            streams = self.workstreams(project)
            if len(streams) < per_project:
                raise RuntimeError(f"project {project['id']} exposes only {len(streams)} public workstreams")
            for stream in streams[: self.config["buildersPerRepository"]["max"]]:
                candidates.append((project, stream))

        if len(candidates) < target:
            target = len(candidates)
        if target < self.config["targetFanout"]["min"]:
            raise RuntimeError("insufficient independent workstreams for configured minimum fan-out")

        leased = time.time()
        ttl = float(self.config.get("leaseTtlSeconds", 1800))
        generation_id = f"{cycle_id}:g{generation}"
        leases: list[Lease] = []
        for index, (project, stream) in enumerate(candidates[:target]):
            stream_id = str(stream["id"])
            exact_sha = exact_refs[project["id"]]
            item_id = stable(cycle_id, generation_id, project["id"], stream_id)
            command = stream.get("command")
            commands = (str(command),) if command else tuple(str(x) for x in stream.get("commands", []))
            leases.append(
                Lease(
                    cycleId=cycle_id,
                    generation=generation,
                    generationId=generation_id,
                    workItemId=item_id,
                    shard=shards[index],
                    projectId=project["id"],
                    repository=project["repository"],
                    targetLane=project.get("integrationLane", "main"),
                    exactInputSha=exact_sha,
                    title=str(stream["title"]),
                    kind=str(stream.get("kind", "verification")),
                    priority=str(stream.get("priority", "P1")),
                    dependencies=tuple(str(x) for x in stream.get("dependencies", [])),
                    verticalSlice=stream_id,
                    collisionDomain=str(stream.get("collisionDomain", f"{project['id']}:public-fabric:{stream_id}")),
                    verification=str(stream.get("verification", "exit-zero+exact-sha")),
                    humanGate=stream.get("humanGate"),
                    idempotencyKey=stable(project["id"], stream_id, exact_sha),
                    status="leased",
                    leasedEpoch=leased,
                    leaseExpiresEpoch=leased + ttl,
                    attempt=1,
                    maxAttempts=int(stream.get("maxAttempts", 2)),
                    commands=commands,
                )
            )

        self.validate(leases)
        return leases

    @staticmethod
    def validate(leases: list[Lease]) -> None:
        fields = {
            "workItemId": [x.workItemId for x in leases],
            "idempotencyKey": [x.idempotencyKey for x in leases],
            "shard": [x.shard for x in leases],
            "collisionDomain": [x.collisionDomain for x in leases],
        }
        for name, values in fields.items():
            if len(values) != len(set(values)):
                raise RuntimeError(f"duplicate {name} in wave")
        if any(x.humanGate for x in leases):
            raise RuntimeError("human-gated work cannot enter public execution wave")


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

    def dispatch(self, owner: str, shard: str, event: str, lease: Lease) -> None:
        envelope = {
            "schema": "razzo.work-item-envelope.v2",
            "workItemId": lease.workItemId,
            "lease": asdict(lease),
        }
        self.request(
            "POST",
            f"https://api.github.com/repos/{owner}/{shard}/dispatches",
            {"event_type": event, "client_payload": envelope},
        )


class ReceiptVerifier:
    REQUIRED = {
        "cycleId",
        "generation",
        "generationId",
        "workItemId",
        "shard",
        "projectId",
        "status",
        "startedEpoch",
        "endedEpoch",
        "exactInputSha",
        "observedSha",
    }

    def verify(self, receipt: dict[str, Any], lease: Lease) -> dict[str, Any]:
        missing = sorted(self.REQUIRED - set(receipt))
        if missing:
            return {"ok": False, "error": f"missing fields: {missing}"}
        if receipt["workItemId"] != lease.workItemId or receipt["shard"] != lease.shard:
            return {"ok": False, "error": "lease identity mismatch"}
        if receipt["generationId"] != lease.generationId or receipt["projectId"] != lease.projectId:
            return {"ok": False, "error": "generation/project identity mismatch"}
        if receipt["status"] != "completed":
            return {"ok": False, "error": receipt.get("error", "shard failed")}
        if receipt["exactInputSha"] != lease.exactInputSha or receipt["observedSha"] != lease.exactInputSha:
            return {"ok": False, "error": "exact SHA mismatch"}
        if float(receipt["endedEpoch"]) < float(receipt["startedEpoch"]):
            return {"ok": False, "error": "invalid execution interval"}
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
    leases = planner.materialize(cycle, 1, refs)
    aggregate = {
        "cycleId": cycle,
        "status": "green",
        "mode": "PUBLIC_FABRIC_CONTRACT_PROOF",
        "configuredShards": len(cfg["shards"]),
        "logicalWorkItems": len(leases),
        "projects": sorted({x.projectId for x in leases}),
        "uniqueCollisionDomains": len({x.collisionDomain for x in leases}),
        "uniqueIdempotencyKeys": len({x.idempotencyKey for x in leases}),
        "targetFanout": cfg["targetFanout"],
        "receiptPerJob": cfg["receiptPerJob"],
        "aggregateReceipt": cfg["aggregateReceipt"],
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "leases.json").write_text(json.dumps([asdict(x) for x in leases], indent=2) + "\n")
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
    planned = [asdict(x) for x in leases]
    queue = {
        "schema": "razzo.public-queue.v1",
        "cycleId": cycle,
        "generationId": leases[0].generationId,
        "createdEpoch": time.time(),
        "status": "dispatching",
        "workItems": planned,
    }
    (output / "queue-manifest.json").write_text(json.dumps(queue, indent=2) + "\n")
    (output / "planned-leases.json").write_text(json.dumps(planned, indent=2) + "\n")

    dispatched: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for lease in leases:
        try:
            api.dispatch(cfg["owner"], lease.shard, cfg["dispatchEvent"], lease)
            row = asdict(lease)
            row["status"] = "dispatched"
            row["dispatchedEpoch"] = time.time()
            dispatched.append(row)
        except Exception as exc:
            failures.append({"workItemId": lease.workItemId, "shard": lease.shard, "error": str(exc)})

    queue["status"] = "dispatched" if not failures else "dispatch-failed"
    queue["workItems"] = dispatched
    queue["dispatchFailures"] = failures
    (output / "queue-manifest.json").write_text(json.dumps(queue, indent=2) + "\n")
    (output / "dispatched-leases.json").write_text(json.dumps(dispatched, indent=2) + "\n")
    (output / "dispatch-failures.json").write_text(json.dumps(failures, indent=2) + "\n")
    if failures:
        raise RuntimeError(f"{len(failures)} of {len(leases)} shard dispatches failed")
    return {
        "cycleId": cycle,
        "generationId": leases[0].generationId,
        "status": "dispatched",
        "leases": len(dispatched),
        "projects": sorted({x.projectId for x in leases}),
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
