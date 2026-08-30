from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path

OWNER = "giovannifidel-collab"
CONTROL_REPO = f"{OWNER}/pfarma-ci"
EVENT = "razzo-work-item"
SHARDS = [
    "razzo-shard-0003", "razzo-shard-0004", "razzo-shard-0008", "razzo-shard-0009",
    "razzo-shard-0016", "razzo-shard-0018", "razzo-shard-0019", "razzo-shard-0020",
    "razzo-shard-0023", "razzo-shard-0024", "razzo-shard-0027", "razzo-shard-0032",
]
TASKS = [
    ("build-make", "https://github.com/crdroidandroid/android_build.git", "14.0"),
    ("build-soong", "https://github.com/crdroidandroid/android_build_soong.git", "14.0"),
    ("frameworks-base", "https://github.com/crdroidandroid/android_frameworks_base.git", "14.0"),
    ("frameworks-native", "https://github.com/crdroidandroid/android_frameworks_native.git", "14.0"),
    ("frameworks-av", "https://github.com/crdroidandroid/android_frameworks_av.git", "14.0"),
    ("system-core", "https://github.com/crdroidandroid/android_system_core.git", "14.0"),
    ("system-sepolicy", "https://github.com/crdroidandroid/android_system_sepolicy.git", "14.0"),
    ("art", "https://github.com/crdroidandroid/android_art.git", "14.0"),
    ("bionic", "https://github.com/crdroidandroid/android_bionic.git", "14.0"),
    ("settings", "https://github.com/crdroidandroid/android_packages_apps_Settings.git", "14.0"),
    ("connectivity", "https://github.com/crdroidandroid/android_packages_modules_Connectivity.git", "14.0"),
    ("hardware-interfaces", "https://github.com/crdroidandroid/android_hardware_interfaces.git", "14.0"),
]


def stable(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


def request(url: str, token: str, payload: dict) -> None:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=45) as response:
        if response.status not in (200, 201, 204):
            raise RuntimeError(f"dispatch failed HTTP {response.status}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=Path("gio-build-dispatch"))
    p.add_argument("--source-sha", required=True)
    args = p.parse_args()

    token = os.environ.get("RAZZO_FABRIC_TOKEN", "").strip()
    if not token:
        raise RuntimeError("missing RAZZO_FABRIC_TOKEN")
    if len(args.source_sha) != 40:
        raise RuntimeError("source SHA must be exact 40-char commit")

    now = time.time()
    cycle = f"gio-os-source-probe-{args.source_sha[:12]}-{int(now)}"
    rows = []
    for index, (task_id, repo, ref) in enumerate(TASKS):
        shard = SHARDS[index]
        work_id = stable(cycle, task_id, shard)
        command = (
            "python3 razzo/gio_os_build/shard_task.py probe "
            f"--task-id {task_id} --repo {repo} --ref {ref}"
        )
        lease = {
            "cycleId": cycle,
            "generation": 1,
            "generationId": f"{cycle}:g1",
            "workItemId": work_id,
            "shard": shard,
            "projectId": "gio-os-public-build",
            "repository": CONTROL_REPO,
            "targetLane": "gio-os-distributed-build",
            "exactInputSha": args.source_sha,
            "title": f"GIO OS public Android source probe: {task_id}",
            "kind": "gio-public-build-probe",
            "priority": "P0",
            "dependencies": [],
            "verticalSlice": task_id,
            "collisionDomain": f"gio-os:source-probe:{task_id}",
            "verification": "exact-sha+public-inputs-only+working-set",
            "humanGate": None,
            "idempotencyKey": stable("gio-os", args.source_sha, task_id),
            "status": "leased",
            "leasedEpoch": now,
            "leaseExpiresEpoch": now + 3600,
            "attempt": 1,
            "maxAttempts": 2,
            "commands": [command],
        }
        envelope = {"schema": "razzo.work-item-envelope.v2", "workItemId": work_id, "lease": lease}
        request(
            f"https://api.github.com/repos/{OWNER}/{shard}/dispatches",
            token,
            {"event_type": EVENT, "client_payload": envelope},
        )
        rows.append({"taskId": task_id, "shard": shard, "workItemId": work_id, "repository": repo, "ref": ref})
        print(f"DISPATCHED {task_id} -> {shard}")

    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "gio.os.distributed-source-probe-wave.v1",
        "cycleId": cycle,
        "controllerSha": args.source_sha,
        "publicWorkerCount": len(rows),
        "targetMaxWorkerWorkingSetGiB": 12.5,
        "privateGioSourceAllowedOnWorkers": False,
        "signingKeysAllowedOnWorkers": False,
        "tasks": rows,
    }
    (args.output / "dispatch-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
