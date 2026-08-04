#!/usr/bin/env python3
from __future__ import annotations

import os
import pathlib
import shutil
import socket
import subprocess
import urllib.request


def run(*args: str, cwd: pathlib.Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def main() -> None:
    token = os.environ.get("RUNNER_TOKEN")
    if not token:
        raise SystemExit("RUNNER_TOKEN is required and must be short-lived")
    url = os.environ.get("RUNNER_URL", "https://github.com/giovannifidel-collab")
    name = os.environ.get("RUNNER_NAME", f"razzo-persistent-{socket.gethostname()}")
    version = os.environ.get("RUNNER_VERSION", "2.336.0")
    root = pathlib.Path(os.environ.get("RAZZO_RUNNER_ROOT", "/opt/razzo"))
    runner = root / "runner"
    cache = root / "cache"
    work = root / "work"
    for path in (runner, cache, work):
        path.mkdir(parents=True, exist_ok=True)
    config = runner / "config.sh"
    if not config.exists():
        archive = runner / "actions-runner.tar.gz"
        source = f"https://github.com/actions/runner/releases/download/v{version}/actions-runner-linux-x64-{version}.tar.gz"
        urllib.request.urlretrieve(source, archive)
        run("tar", "xzf", str(archive), cwd=runner)
    run(
        str(config), "--unattended", "--replace", "--url", url, "--token", token,
        "--name", name, "--labels", "razzo-persistent,linux,x64", "--work", str(work), cwd=runner,
    )
    svc = runner / "svc.sh"
    if shutil.which("sudo"):
        run("sudo", str(svc), "install", os.environ.get("USER", "root"), cwd=runner)
        run("sudo", str(svc), "start", cwd=runner)
    else:
        raise SystemExit("sudo is required to install the runner service")
    print(f"RAZZO persistent runner installed: {name}")


if __name__ == "__main__":
    main()
