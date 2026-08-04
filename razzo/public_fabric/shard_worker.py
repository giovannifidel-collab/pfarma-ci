from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


def run(command: list[str], cwd: Path | None = None, capture: bool = False) -> str:
    result = subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=capture)
    return result.stdout.strip() if capture else ""


def unwrap_payload(raw: dict[str, Any]) -> dict[str, Any]:
    payload = raw.get("lease", raw)
    if not isinstance(payload, dict):
        raise RuntimeError("invalid work-item envelope")
    return payload


def execute(payload: dict[str, Any], output: Path) -> dict[str, Any]:
    started = time.time()
    shard = os.environ.get("GITHUB_REPOSITORY", "unknown/unknown").split("/")[-1]
    receipt: dict[str, Any] = {
        "cycleId": payload["cycleId"],
        "generation": payload["generation"],
        "workItemId": payload["workItemId"],
        "shard": shard,
        "projectId": payload["projectId"],
        "repository": payload["repository"],
        "exactInputSha": payload["exactInputSha"],
        "collisionDomain": payload["collisionDomain"],
        "attempt": payload.get("attempt", 1),
        "startedEpoch": started,
        "status": "running",
    }
    try:
        token = os.environ.get("RAZZO_FABRIC_TOKEN")
        if not token:
            raise RuntimeError("missing RAZZO_FABRIC_TOKEN")
        work = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / payload["workItemId"]
        auth = f"https://x-access-token:{token}@github.com/{payload['repository']}.git"
        run(["git", "clone", "--filter=blob:none", "--no-checkout", auth, str(work)])
        run(["git", "checkout", payload["exactInputSha"]], cwd=work)
        observed = run(["git", "rev-parse", "HEAD"], cwd=work, capture=True)
        if observed != payload["exactInputSha"]:
            raise RuntimeError("exact SHA mismatch after checkout")
        commands = payload.get("commands") or []
        results: list[dict[str, Any]] = []
        for command in commands:
            if not isinstance(command, list) or not command:
                raise RuntimeError("commands must be non-empty argv arrays")
            started_cmd = time.time()
            run([str(x) for x in command], cwd=work)
            results.append({"argv": command, "durationSeconds": round(time.time() - started_cmd, 3), "ok": True})
        receipt.update({"status": "completed", "observedSha": observed, "commands": results})
    except Exception as exc:
        receipt.update({"status": "failed", "error": str(exc)})
    receipt["endedEpoch"] = time.time()
    receipt["durationSeconds"] = round(receipt["endedEpoch"] - started, 3)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    raw_payload = json.loads(os.environ["RAZZO_WORK_ITEM"])
    payload = unwrap_payload(raw_payload)
    receipt = execute(payload, Path("receipt.json"))
    print(json.dumps(receipt, indent=2))
    raise SystemExit(0 if receipt["status"] == "completed" else 2)
