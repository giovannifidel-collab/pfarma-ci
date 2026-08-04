from __future__ import annotations

import base64
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


def run(command: list[str], cwd: Path | None = None, capture: bool = False) -> str:
    result = subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=capture)
    return result.stdout.strip() if capture else ""


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
        "schema": "razzo.receipt-envelope.v1",
        "workItemId": receipt["workItemId"],
        "receipt": receipt,
    }
    request(
        "POST",
        f"https://api.github.com/repos/{CONTROL_REPOSITORY}/dispatches",
        token,
        {"event_type": "razzo-receipt", "client_payload": envelope},
    )


def execute(lease: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    shard = os.environ["GITHUB_REPOSITORY"].split("/")[-1]
    receipt: dict[str, Any] = {
        "cycleId": lease["cycleId"],
        "generation": lease["generation"],
        "workItemId": lease["workItemId"],
        "shard": shard,
        "projectId": lease["projectId"],
        "repository": lease["repository"],
        "exactInputSha": lease["exactInputSha"],
        "collisionDomain": lease["collisionDomain"],
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
        run(["git", "clone", "--filter=blob:none", "--no-checkout", auth, str(work)])
        run(["git", "checkout", lease["exactInputSha"]], cwd=work)
        observed = run(["git", "rev-parse", "HEAD"], cwd=work, capture=True)
        if observed != lease["exactInputSha"]:
            raise RuntimeError("exact SHA mismatch after checkout")
        results: list[dict[str, Any]] = []
        for command in lease.get("commands") or []:
            if not isinstance(command, list) or not command:
                raise RuntimeError("commands must be non-empty argv arrays")
            command_started = time.time()
            run([str(item) for item in command], cwd=work)
            results.append(
                {
                    "argv": command,
                    "durationSeconds": round(time.time() - command_started, 3),
                    "ok": True,
                }
            )
        receipt.update({"status": "completed", "observedSha": observed, "commands": results})
    except Exception as exc:
        receipt.update({"status": "failed", "error": str(exc)})
    receipt["endedEpoch"] = time.time()
    receipt["durationSeconds"] = round(receipt["endedEpoch"] - started, 3)
    Path("receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def status_from(lease: dict[str, Any], state: str, receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    receipt = receipt or {}
    return {
        "schema": "razzo.public-worker-status.v1",
        "state": state,
        "workflowRunId": os.environ.get("GITHUB_RUN_ID"),
        "cycleId": lease["cycleId"],
        "workItemId": lease["workItemId"],
        "shard": os.environ["GITHUB_REPOSITORY"].split("/")[-1],
        "projectId": lease["projectId"],
        "repository": lease["repository"],
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
