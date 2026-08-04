from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

STATUS_PATH = "razzo-public-worker-status.json"
CONTROL_REPOSITORY = "giovannifidel-collab/pfarma-ci"
MAX_SCAN_FILES = 5000
MAX_SCAN_BYTES = 2_000_000


def request(method: str, url: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=45) as response:
        body = response.read().decode()
        return json.loads(body) if body else {}


def unwrap(raw: dict[str, Any]) -> dict[str, Any]:
    lease = raw.get("lease", raw)
    if not isinstance(lease, dict):
        raise RuntimeError("invalid work-item envelope")
    required = {
        "cycleId",
        "generation",
        "generationId",
        "workItemId",
        "projectId",
        "repository",
        "exactInputSha",
        "title",
        "kind",
        "collisionDomain",
        "verification",
        "idempotencyKey",
        "status",
        "leaseExpiresEpoch",
    }
    missing = sorted(required - set(lease))
    if missing:
        raise RuntimeError(f"missing lease fields: {missing}")
    if lease.get("humanGate"):
        raise RuntimeError("human-gated work cannot execute on public shard")
    if lease["status"] != "leased":
        raise RuntimeError("work item is not leased")
    if float(lease["leaseExpiresEpoch"]) <= time.time():
        raise RuntimeError("lease expired before execution")
    return lease


def upsert_status(status: dict[str, Any]) -> None:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repository = os.environ["GITHUB_REPOSITORY"]
    if not token:
        raise RuntimeError("missing shard GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{repository}/contents/{STATUS_PATH}"
    sha = None
    try:
        sha = request("GET", url, token)["sha"]
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    body: dict[str, Any] = {
        "message": f"RAZZO status: {status['state']} {status['workItemId']}",
        "content": base64.b64encode((json.dumps(status, indent=2) + "\n").encode()).decode(),
        "branch": "main",
    }
    if sha:
        body["sha"] = sha
    request("PUT", url, token, body)


def publish_receipt(receipt: dict[str, Any]) -> None:
    token = os.environ.get("RAZZO_FABRIC_TOKEN", "").strip()
    if not token:
        raise RuntimeError("missing RAZZO_FABRIC_TOKEN for receipt callback")
    envelope = {
        "schema": "razzo.receipt-envelope.v2",
        "workItemId": receipt["workItemId"],
        "receipt": receipt,
    }
    request(
        "POST",
        f"https://api.github.com/repos/{CONTROL_REPOSITORY}/dispatches",
        token,
        {"event_type": "razzo-receipt", "client_payload": envelope},
    )


def run_git(command: list[str], cwd: Path | None = None, capture: bool = False) -> str:
    completed = subprocess.run(command, cwd=cwd, text=False, capture_output=True, timeout=300)
    output = (completed.stdout or b"") + b"\n" + (completed.stderr or b"")
    if completed.returncode != 0:
        digest = hashlib.sha256(output).hexdigest()
        raise RuntimeError(f"git operation failed with exit code {completed.returncode}; output digest {digest}")
    return (completed.stdout or b"").decode("utf-8", errors="replace").strip() if capture else ""


def run_shell(command: str, cwd: Path, command_id: str) -> dict[str, Any]:
    started = time.time()
    completed = subprocess.run(
        ["bash", "-lc", command],
        cwd=cwd,
        text=False,
        capture_output=True,
        timeout=1200,
    )
    output = (completed.stdout or b"") + b"\n" + (completed.stderr or b"")
    result = {
        "commandId": command_id,
        "durationSeconds": round(time.time() - started, 3),
        "exitCode": completed.returncode,
        "outputBytes": len(output),
        "outputDigest": hashlib.sha256(output).hexdigest(),
    }
    if completed.returncode != 0:
        raise RuntimeError(
            f"command {command_id} failed with exit code {completed.returncode}; output digest {result['outputDigest']}"
        )
    return result


def discovery_metrics(work: Path) -> dict[str, Any]:
    files = 0
    tests = 0
    todos = 0
    fixmes = 0
    placeholders = 0
    mocks = 0
    bytes_scanned = 0
    extensions: dict[str, int] = {}
    path_digest = hashlib.sha256()
    ignored = {".git", "node_modules", ".next", "dist", "build", "coverage", ".venv", "venv"}
    for path in sorted(work.rglob("*")):
        if files >= MAX_SCAN_FILES:
            break
        if not path.is_file() or any(part in ignored for part in path.parts):
            continue
        relative = path.relative_to(work).as_posix()
        files += 1
        path_digest.update(relative.encode())
        path_digest.update(str(path.stat().st_size).encode())
        suffix = path.suffix.lower() or "<none>"
        extensions[suffix] = extensions.get(suffix, 0) + 1
        lower_name = relative.lower()
        if "test" in lower_name or "spec" in lower_name:
            tests += 1
        try:
            data = path.read_bytes()[:MAX_SCAN_BYTES]
        except OSError:
            continue
        bytes_scanned += len(data)
        text = data.decode("utf-8", errors="ignore").lower()
        todos += text.count("todo")
        fixmes += text.count("fixme")
        placeholders += text.count("placeholder")
        mocks += text.count("mock")
    top_extensions = sorted(extensions.items(), key=lambda item: (-item[1], item[0]))[:12]
    return {
        "fileCount": files,
        "testLikeFileCount": tests,
        "todoMarkerCount": todos,
        "fixmeMarkerCount": fixmes,
        "placeholderMarkerCount": placeholders,
        "mockMarkerCount": mocks,
        "bytesScanned": bytes_scanned,
        "topExtensions": top_extensions,
        "repositoryShapeDigest": path_digest.hexdigest(),
        "truncated": files >= MAX_SCAN_FILES,
    }


def execute(lease: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    shard = os.environ["GITHUB_REPOSITORY"].split("/")[-1]
    receipt: dict[str, Any] = {
        "cycleId": lease["cycleId"],
        "generation": lease["generation"],
        "generationId": lease["generationId"],
        "workItemId": lease["workItemId"],
        "shard": shard,
        "projectId": lease["projectId"],
        "repository": lease["repository"],
        "targetLane": lease.get("targetLane"),
        "exactInputSha": lease["exactInputSha"],
        "title": lease["title"],
        "kind": lease["kind"],
        "priority": lease.get("priority"),
        "collisionDomain": lease["collisionDomain"],
        "verification": lease["verification"],
        "idempotencyKey": lease["idempotencyKey"],
        "attempt": lease.get("attempt", 1),
        "startedEpoch": started,
        "status": "running",
    }
    try:
        token = os.environ.get("RAZZO_FABRIC_TOKEN", "").strip()
        if not token:
            raise RuntimeError("missing RAZZO_FABRIC_TOKEN")
        work = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / lease["workItemId"]
        auth = f"https://x-access-token:{token}@github.com/{lease['repository']}.git"
        run_git(["git", "clone", "--filter=blob:none", "--no-checkout", "--quiet", auth, str(work)])
        run_git(["git", "checkout", "--quiet", lease["exactInputSha"]], cwd=work)
        observed = run_git(["git", "rev-parse", "HEAD"], cwd=work, capture=True)
        if observed != lease["exactInputSha"]:
            raise RuntimeError("exact SHA mismatch after checkout")
        receipt["observedSha"] = observed

        results: list[dict[str, Any]] = []
        for index, command in enumerate(lease.get("commands") or []):
            if not isinstance(command, str) or not command.strip():
                raise RuntimeError("commands must be non-empty shell strings")
            results.append(run_shell(command, work, f"cmd-{index + 1}"))

        metrics = discovery_metrics(work) if lease["kind"] == "discovery" else None
        receipt.update(
            {
                "status": "completed",
                "observedSha": observed,
                "commands": results,
                "metrics": metrics,
            }
        )
    except Exception as exc:
        receipt.update({"status": "failed", "error": str(exc)})
    receipt["endedEpoch"] = time.time()
    receipt["durationSeconds"] = round(receipt["endedEpoch"] - started, 3)
    Path("receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def status_from(lease: dict[str, Any], state: str, receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    receipt = receipt or {}
    return {
        "schema": "razzo.public-worker-status.v2",
        "state": state,
        "workflowRunId": os.environ.get("GITHUB_RUN_ID"),
        "cycleId": lease["cycleId"],
        "generationId": lease["generationId"],
        "workItemId": lease["workItemId"],
        "shard": os.environ["GITHUB_REPOSITORY"].split("/")[-1],
        "projectId": lease["projectId"],
        "repository": lease["repository"],
        "title": lease["title"],
        "kind": lease["kind"],
        "exactInputSha": lease["exactInputSha"],
        "observedSha": receipt.get("observedSha"),
        "durationSeconds": receipt.get("durationSeconds"),
        "error": receipt.get("error"),
        "updatedEpoch": time.time(),
    }


def main() -> int:
    raw = json.loads(os.environ["RAZZO_WORK_ITEM"])
    lease = unwrap(raw)
    receipt: dict[str, Any] | None = None
    try:
        upsert_status(status_from(lease, "started"))
        receipt = execute(lease)
        try:
            publish_receipt(receipt)
        except Exception as callback_error:
            receipt["callbackError"] = str(callback_error)
            Path("receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        return 0 if receipt["status"] == "completed" else 2
    finally:
        if receipt is None:
            now = time.time()
            receipt = {
                "status": "failed",
                "startedEpoch": now,
                "endedEpoch": now,
                "durationSeconds": 0,
                "error": "entrypoint terminated before receipt creation",
            }
        upsert_status(status_from(lease, receipt.get("status", "failed"), receipt))


if __name__ == "__main__":
    raise SystemExit(main())
