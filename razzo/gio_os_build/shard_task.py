from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

MAX_WORKING_SET_GIB = 12.5
ALLOWED = re.compile(r"^https://github\.com/(?:crdroidandroid|LineageOS|aosp-mirror)/[A-Za-z0-9_.-]+(?:\.git)?$")


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 1200) -> str:
    p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if p.returncode:
        digest = hashlib.sha256((p.stdout or b"") + (p.stderr or b"")).hexdigest()
        raise RuntimeError(f"command failed rc={p.returncode} digest={digest}")
    return (p.stdout or b"").decode("utf-8", errors="replace").strip()


def api(method: str, url: str, token: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=45) as r:
        body = r.read().decode()
        return json.loads(body) if body else {}


def resolve(repo: str, ref: str) -> str:
    if not ALLOWED.fullmatch(repo):
        raise RuntimeError("upstream repository is outside the public allowlist")
    if re.fullmatch(r"[0-9a-f]{40}", ref):
        return ref
    rows = run(["git", "ls-remote", repo, ref, f"refs/heads/{ref}", f"refs/tags/{ref}"]).splitlines()
    shas = []
    for row in rows:
        parts = row.split()
        if len(parts) == 2 and re.fullmatch(r"[0-9a-f]{40}", parts[0]):
            shas.append(parts[0])
    if not shas:
        raise RuntimeError(f"cannot resolve public ref {ref}")
    return shas[0]


def dir_kib(path: Path) -> int:
    return int(run(["du", "-sk", str(path)]).split()[0])


def top_dirs(path: Path) -> list[dict]:
    rows = []
    for child in path.iterdir():
        if child.name == ".git":
            continue
        try:
            kib = dir_kib(child)
        except Exception:
            continue
        rows.append({"path": child.name, "kib": kib})
    rows.sort(key=lambda x: x["kib"], reverse=True)
    return rows[:12]


def publish(result: dict) -> None:
    out = Path("fabric-output")
    out.mkdir(exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    shard_repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not shard_repo.startswith("giovannifidel-collab/razzo-shard-"):
        return
    url = f"https://api.github.com/repos/{shard_repo}/contents/gio-build-result.json"
    sha = None
    try:
        sha = api("GET", url, token).get("sha")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    payload = {
        "message": f"gio build probe: {result['taskId']}",
        "branch": "main",
        "content": base64.b64encode((json.dumps(result, indent=2, sort_keys=True) + "\n").encode()).decode(),
    }
    if sha:
        payload["sha"] = sha
    api("PUT", url, token, payload)


def probe(task_id: str, repo: str, ref: str) -> dict:
    source_sha = resolve(repo, ref)
    root = Path(tempfile.mkdtemp(prefix="gio-public-probe-"))
    src = root / "src"
    try:
        run(["git", "-c", "protocol.version=2", "clone", "--filter=blob:none", "--no-checkout", "--quiet", repo, str(src)])
        run(["git", "fetch", "--depth=1", "origin", source_sha], cwd=src)
        run(["git", "checkout", "--detach", "--quiet", "FETCH_HEAD"], cwd=src)
        observed = run(["git", "rev-parse", "HEAD"], cwd=src)
        if observed != source_sha:
            raise RuntimeError("resolved SHA mismatch")
        kib = dir_kib(src)
        file_count = int(run(["bash", "-lc", "find . -type f -not -path './.git/*' | wc -l"], cwd=src))
        git_kib = dir_kib(src / ".git")
        result = {
            "schema": "gio.os.public-source-probe.v1",
            "taskId": task_id,
            "repository": repo,
            "requestedRef": ref,
            "resolvedSha": source_sha,
            "workingSetKiB": kib,
            "workingSetGiB": round(kib / 1024 / 1024, 3),
            "gitMetadataGiB": round(git_kib / 1024 / 1024, 3),
            "fileCount": file_count,
            "topDirectories": top_dirs(src),
            "targetMaxGiB": MAX_WORKING_SET_GIB,
            "withinTarget": kib <= int(MAX_WORKING_SET_GIB * 1024 * 1024),
            "publicInputsOnly": True,
            "privateGioSourcePresent": False,
            "signingKeysPresent": False,
        }
        publish(result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return result
    finally:
        shutil.rmtree(root, ignore_errors=True)


def self_test() -> None:
    assert ALLOWED.fullmatch("https://github.com/crdroidandroid/android_build.git")
    assert not ALLOWED.fullmatch("https://github.com/giovannifidel-collab/gio-OS.git")
    assert not ALLOWED.fullmatch("https://example.com/repo.git")
    print("GIO_PUBLIC_SHARD_CONTRACT=PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("self-test")
    q = sub.add_parser("probe")
    q.add_argument("--task-id", required=True)
    q.add_argument("--repo", required=True)
    q.add_argument("--ref", required=True)
    a = p.parse_args()
    if a.cmd == "self-test":
        self_test()
    else:
        probe(a.task_id, a.repo, a.ref)


if __name__ == "__main__":
    main()
