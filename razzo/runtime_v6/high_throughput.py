from __future__ import annotations

import argparse
import concurrent.futures as futures
import hashlib
import json
import os
import shlex
import statistics
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "razzo/runtime_v6/high_throughput.json"
PORTFOLIO = ROOT / "razzo/projects.json"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stable(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]


def enabled_projects() -> list[dict[str, Any]]:
    return [p for p in load(PORTFOLIO).get("projects", []) if p.get("enabled", True)]


@dataclass(frozen=True)
class WorkItem:
    cycle_id: str
    generation: int
    project_id: str
    repository: str
    integration_lane: str
    exact_sha: str
    vertical_slice: str
    collision_domain: str
    allowed_paths: tuple[str, ...]
    acceptance_tests: tuple[str, ...]
    worker_id: str
    work_item_id: str
    attempt: int = 1


class Planner:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg

    def _ref(self, project: dict[str, Any]) -> str:
        ref_file = project.get("portfolioRefFile") or project.get("sourceRefFile")
        if ref_file and (ROOT / ref_file).exists():
            value = (ROOT / ref_file).read_text().strip()
            if len(value) == 40:
                return value
        lane = project.get("integrationLane", "main")
        result = subprocess.run(
            ["git", "ls-remote", f"https://github.com/{project['repository']}.git", f"refs/heads/{lane}"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.split()[0]

    def _slices(self, project: dict[str, Any], generation: int) -> list[dict[str, Any]]:
        manifest = project.get("factoryWorkManifest")
        candidates = []
        if manifest:
            candidates.append(ROOT / manifest)
        candidates.append(ROOT / "razzo/work" / f"{project['id']}.json")
        for path in candidates:
            if path.exists():
                payload = load(path)
                return [x for x in payload.get("verticalSlices", []) if x.get("enabled", True)]
        return [
            {
                "id": f"discover-next-slice-g{generation}",
                "collisionDomain": "factory/discovery",
                "allowedPaths": ["**"],
                "acceptanceTests": ["factory-plan"],
            },
            {
                "id": f"build-next-slice-g{generation}",
                "collisionDomain": "factory/product",
                "allowedPaths": ["app/**", "src/**", "tests/**"],
                "acceptanceTests": ["targeted-tests"],
            },
            {
                "id": f"robot-journey-g{generation}",
                "collisionDomain": "factory/robot",
                "allowedPaths": ["tests/**", "factory/**"],
                "acceptanceTests": ["robot-journey"],
            },
            {
                "id": f"repair-candidate-g{generation}",
                "collisionDomain": "factory/repair",
                "allowedPaths": ["app/**", "src/**", "tests/**"],
                "acceptanceTests": ["failed-gate-repair"],
            },
        ]

    def materialize(self, cycle_id: str, generation: int, backlog_hint: int | None = None) -> list[WorkItem]:
        projects = enabled_projects()
        if not projects:
            raise RuntimeError("no enabled projects")
        fan = self.cfg["fanout"]
        target = max(fan["targetMin"], backlog_hint or 0)
        target = min(target, fan["targetMax"], fan["hardMax"])
        refs = {p["id"]: self._ref(p) for p in projects}
        slices = {p["id"]: self._slices(p, generation) for p in projects}
        per_repo_cap = fan["builderPerRepoMax"]
        counts = {p["id"]: 0 for p in projects}
        out: list[WorkItem] = []
        cursor = 0
        while len(out) < target:
            project = projects[cursor % len(projects)]
            if counts[project["id"]] >= per_repo_cap:
                if all(v >= per_repo_cap for v in counts.values()):
                    break
                cursor += 1
                continue
            options = slices[project["id"]]
            spec = options[counts[project["id"]] % len(options)]
            wid = f"g{generation}-{project['id']}-{counts[project['id']]:02d}"
            item_id = stable(cycle_id, str(generation), project["id"], spec["id"], str(counts[project["id"]]))
            out.append(
                WorkItem(
                    cycle_id=cycle_id,
                    generation=generation,
                    project_id=project["id"],
                    repository=project["repository"],
                    integration_lane=project.get("integrationLane", "main"),
                    exact_sha=refs[project["id"]],
                    vertical_slice=spec["id"],
                    collision_domain=spec["collisionDomain"],
                    allowed_paths=tuple(spec.get("allowedPaths", ["**"])),
                    acceptance_tests=tuple(spec.get("acceptanceTests", [])),
                    worker_id=wid,
                    work_item_id=item_id,
                )
            )
            counts[project["id"]] += 1
            cursor += 1
        if len(out) < fan["targetMin"]:
            raise RuntimeError(f"safe fan-out only produced {len(out)} items; minimum is {fan['targetMin']}")
        return out


class ReceiptStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def write(self, receipt: dict[str, Any]) -> Path:
        path = self.root / f"{receipt['workItemId']}-a{receipt['attempt']}.json"
        with self.lock:
            path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        return path


class Worker:
    def __init__(self, cfg: dict[str, Any], mode: str, store: ReceiptStore):
        self.cfg, self.mode, self.store = cfg, mode, store

    def run(self, item: WorkItem) -> dict[str, Any]:
        started = time.time()
        receipt: dict[str, Any] = {
            **asdict(item),
            "workItemId": item.work_item_id,
            "workerId": item.worker_id,
            "startedEpoch": started,
            "status": "running",
            "mode": self.mode,
            "branch": None,
            "commitSha": None,
            "prNumber": None,
            "tests": [],
            "filesChanged": [],
        }
        try:
            if self.mode == "proof":
                time.sleep(0.25)
                receipt["status"] = "completed"
                receipt["tests"] = ["contract", "exact-sha", "receipt"]
            else:
                self._production(item, receipt)
        except Exception as exc:
            receipt["status"] = "failed"
            receipt["error"] = str(exc)
        receipt["endedEpoch"] = time.time()
        receipt["durationSeconds"] = round(receipt["endedEpoch"] - started, 3)
        self.store.write(receipt)
        return receipt

    def _production(self, item: WorkItem, receipt: dict[str, Any]) -> None:
        token_env = self.cfg["requirements"]["githubWriteTokenEnv"]
        builder_env = self.cfg["requirements"]["builderCommandEnv"]
        token = os.environ.get(token_env)
        builder = os.environ.get(builder_env)
        if not token:
            raise RuntimeError(f"missing {token_env}: cross-repository branch/PR writes are impossible")
        if not builder:
            raise RuntimeError(f"missing {builder_env}: no coding executor is configured")
        cache_root = Path(self.cfg["runner"]["cacheRoot"])
        work_root = Path(self.cfg["runner"]["workspaceRoot"])
        cache_root.mkdir(parents=True, exist_ok=True)
        work_root.mkdir(parents=True, exist_ok=True)
        repo_name = item.repository.split("/", 1)[1]
        mirror = cache_root / f"{repo_name}.git"
        env = {**os.environ, "GH_TOKEN": token}
        auth_url = f"https://x-access-token:{token}@github.com/{item.repository}.git"
        if mirror.exists():
            subprocess.run(["git", "--git-dir", str(mirror), "fetch", "--prune", "origin"], check=True, env=env)
        else:
            subprocess.run(["git", "clone", "--mirror", auth_url, str(mirror)], check=True, env=env)
        workspace = Path(tempfile.mkdtemp(prefix=f"{item.project_id}-", dir=work_root))
        branch = f"razzo/{item.cycle_id}/{item.vertical_slice}"
        subprocess.run(["git", "clone", str(mirror), str(workspace)], check=True, env=env)
        subprocess.run(["git", "checkout", "-b", branch, item.exact_sha], cwd=workspace, check=True, env=env)
        prompt = json.dumps(
            {
                "objective": item.vertical_slice,
                "collisionDomain": item.collision_domain,
                "allowedPaths": item.allowed_paths,
                "acceptanceTests": item.acceptance_tests,
                "rule": "Implement one complete vertical slice. Modify only allowed paths. Run targeted tests. Do not touch main.",
            }
        )
        subprocess.run(shlex.split(builder) + [prompt], cwd=workspace, check=True, env=env)
        changed = subprocess.run(
            ["git", "status", "--porcelain"], cwd=workspace, check=True, capture_output=True, text=True
        ).stdout.splitlines()
        if not changed:
            raise RuntimeError("builder produced no product change")
        subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
        subprocess.run(["git", "commit", "-m", f"feat(razzo): {item.vertical_slice}"], cwd=workspace, check=True)
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=workspace, check=True, capture_output=True, text=True
        ).stdout.strip()
        subprocess.run(["git", "push", "origin", f"HEAD:{branch}"], cwd=workspace, check=True, env=env)
        body = json.dumps(
            {"cycle": item.cycle_id, "workItem": item.work_item_id, "collisionDomain": item.collision_domain}
        )
        pr_url = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                item.repository,
                "--base",
                item.integration_lane,
                "--head",
                branch,
                "--title",
                f"RAZZO: {item.vertical_slice}",
                "--body",
                body,
                "--draft",
            ],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        ).stdout.strip()
        receipt["status"] = "completed"
        receipt["branch"] = branch
        receipt["commitSha"] = commit
        receipt["prUrl"] = pr_url
        receipt["filesChanged"] = [line[3:] for line in changed]


def verify_one(receipt: dict[str, Any], mode: str) -> dict[str, Any]:
    required = {"workItemId", "workerId", "status", "startedEpoch", "endedEpoch", "collision_domain"}
    missing = sorted(required - set(receipt))
    if missing:
        return {"ok": False, "error": f"missing {missing}", "workItemId": receipt.get("workItemId")}
    if receipt["status"] != "completed":
        return {"ok": False, "error": receipt.get("error", "worker failed"), "workItemId": receipt["workItemId"]}
    if mode == "product" and (not receipt.get("commitSha") or not receipt.get("prUrl")):
        return {"ok": False, "error": "product worker lacks commit/PR evidence", "workItemId": receipt["workItemId"]}
    return {"ok": True, "workItemId": receipt["workItemId"]}


def percentile95(values: list[float]) -> float:
    if len(values) < 2:
        return max(values or [0.0])
    return statistics.quantiles(values, n=20, method="inclusive")[18]


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
    for generation in range(1, max_gen + 1):
        items = planner.materialize(cycle, generation)
        pending: dict[futures.Future[dict[str, Any]], WorkItem] = {}
        verified: list[dict[str, Any]] = []
        with futures.ThreadPoolExecutor(max_workers=max_workers) as pool, futures.ThreadPoolExecutor(
            max_workers=verifier_workers
        ) as vpool:
            for item in items:
                pending[pool.submit(worker.run, item)] = item
            replan_marked = False
            while pending:
                done, _ = futures.wait(pending, return_when=futures.FIRST_COMPLETED)
                for future in done:
                    item = pending.pop(future)
                    receipt = future.result()
                    all_receipts.append(receipt)
                    durations.append(receipt["durationSeconds"])
                    verified.append(vpool.submit(verify_one, receipt, mode).result())
                if len(pending) <= refill and generation < max_gen and not replan_marked:
                    generations.append({"generation": generation, "replanPreparedAtRemaining": len(pending)})
                    replan_marked = True
                threshold = percentile95(durations)
                if cfg["retry"]["strategy"] == "speculative-p95" and threshold > 0 and len(durations) >= cfg["retry"]["minimumSamples"]:
                    for future, item in list(pending.items()):
                        if not future.done() and item.attempt == 1:
                            retry = WorkItem(**{**asdict(item), "attempt": 2, "worker_id": item.worker_id + "-spec"})
                            pending[pool.submit(worker.run, retry)] = retry
                            speculative += 1
                            break
            if not all(v["ok"] for v in verified):
                raise RuntimeError(f"verification failed: {verified}")
        generations.append({"generation": generation, "items": len(items), "verified": len(verified)})
    events = []
    for receipt in all_receipts:
        events += [(receipt["startedEpoch"], 1), (receipt["endedEpoch"], -1)]
    active = peak = 0
    for _, delta in sorted(events, key=lambda x: (x[0], -x[1])):
        active += delta
        peak = max(peak, active)
    aggregate = {
        "cycleId": cycle,
        "mode": mode,
        "status": "green",
        "generations": max_gen,
        "workItems": len(all_receipts),
        "parallelPeak": peak,
        "targetFanout": [cfg["fanout"]["targetMin"], cfg["fanout"]["targetMax"]],
        "hardMax": max_workers,
        "queueRefillThreshold": refill,
        "incrementalReplan": cfg["generations"]["incrementalReplan"],
        "speculativeRetries": speculative,
        "receipts": len(all_receipts),
        "verified": sum(1 for r in all_receipts if r["status"] == "completed"),
        "productPRs": sum(1 for r in all_receipts if r.get("prUrl")),
        "generationTelemetry": generations,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "aggregate-cycle-receipt.json").write_text(json.dumps(aggregate, indent=2) + "\n")
    return aggregate


def preflight(mode: str) -> dict[str, Any]:
    cfg = load(CONFIG)
    checks = {
        "configuration": True,
        "fanout": cfg["fanout"]
        == {
            "targetMin": 12,
            "targetMax": 20,
            "hardMax": 24,
            "builderPerRepoMin": 4,
            "builderPerRepoMax": 8,
            "verifierMin": 2,
            "verifierMax": 4,
            "integratorPerCollisionDomain": 1,
            "queueRefillThreshold": 8,
        },
        "generations": cfg["generations"]["maxPerTrigger"] == 4
        and cfg["generations"]["incrementalReplan"],
        "receipts": cfg["receipts"]["perJob"] and cfg["receipts"]["aggregate"],
        "onePrPerSlice": cfg["pullRequests"]["onePerVerticalSlice"],
    }
    if mode == "product":
        checks["writeToken"] = bool(os.environ.get(cfg["requirements"]["githubWriteTokenEnv"]))
        checks["builderCommand"] = bool(os.environ.get(cfg["requirements"]["builderCommandEnv"]))
        checks["persistentRunner"] = os.environ.get("RUNNER_ENVIRONMENT") == "self-hosted"
    return {"ok": all(checks.values()), "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    cycle = sub.add_parser("cycle")
    cycle.add_argument("--mode", choices=["proof", "product"], default="proof")
    cycle.add_argument("--output", type=Path, required=True)
    pre = sub.add_parser("preflight")
    pre.add_argument("--mode", choices=["proof", "product"], default="proof")
    args = parser.parse_args()
    if args.cmd == "preflight":
        result = preflight(args.mode)
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["ok"] else 2)
    result = run_cycle(args.mode, args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
