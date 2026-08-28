#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
FABRIC = ROOT / "gio-build-fabric"

PRIVATE_CI = WORKFLOWS / "gio-os-private-source-ci.yml"
WORLD_SYNC = WORKFLOWS / "hive-world-sync.yml"


def fail(message: str) -> None:
    raise SystemExit(f"gio-OS safety gate v1: FAIL: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def validate_private_ci() -> None:
    text = PRIVATE_CI.read_text()
    require("GIO_OS_SOURCE_TOKEN ||" not in text, "gio-OS token must never fall back to another project token")
    require("PFARMA_SOURCE_TOKEN" not in text, "gio-OS private-source CI must not reference PFarma source credentials")
    require("if: github.event_name != 'pull_request'" in text, "secret-bearing private-source job must be disabled on pull_request")
    require("permissions:\n      contents: read" in text, "private-source validation job must have read-only repository permissions")
    require("persist-credentials: false" in text, "private-source validation must not persist checkout credentials")
    require("actions/upload-artifact@v4" in text, "sanitized state must cross the trust boundary only as an artifact")
    require("publish-sanitized-state:" in text, "sanitized publication must happen in a separate write-capable job")
    require("needs: validate-private-source" in text, "publication must depend on successful private-source validation")


def validate_world_sync() -> None:
    text = WORLD_SYNC.read_text()
    forbidden = {
        "GIO_OS_SOURCE_TOKEN": "global HIVE sync must not receive the gio-OS private-source token",
        "repository: giovannifidel-collab/gio-OS": "global HIVE sync must not checkout private gio-OS source",
        "path: _sources/gio-os": "global HIVE sync must not materialize the gio-OS source tree",
    }
    for needle, message in forbidden.items():
        require(needle not in text, message)
    require("gio-os-state.json" in text, "global HIVE sync must consume the sanitized gio-OS state relay")


def walk_json(node, path: str = "$") -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            current = f"{path}.{key}"
            if key == "private_source_present":
                require(value is False or (isinstance(value, dict) and value.get("const") is False),
                        f"{current} must be false/const false")
            if key in {"signing_keys", "private_gio_source"}:
                require(value is False, f"{current} must be false")
            walk_json(value, current)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            walk_json(value, f"{path}[{index}]")


def validate_fabric_contracts() -> None:
    require(FABRIC.exists(), "gio-build-fabric directory missing")
    json_files = sorted(FABRIC.rglob("*.json"))
    require(json_files, "no gio build-fabric JSON contracts found")
    for path in json_files:
        try:
            data = json.loads(path.read_text())
        except Exception as exc:
            fail(f"{path.relative_to(ROOT)} is not valid JSON: {exc}")
        walk_json(data, str(path.relative_to(ROOT)))


def validate_secret_scope() -> None:
    allowed = {PRIVATE_CI}
    offenders = []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        text = path.read_text()
        if "GIO_OS_SOURCE_TOKEN" in text and path not in allowed:
            offenders.append(str(path.relative_to(ROOT)))
        if "GIO_OS_SOURCE_TOKEN ||" in text:
            offenders.append(f"{path.relative_to(ROOT)} (cross-project fallback)")
    require(not offenders, "gio-OS private token escaped its dedicated workflow: " + ", ".join(offenders))


def main() -> None:
    validate_private_ci()
    validate_world_sync()
    validate_fabric_contracts()
    validate_secret_scope()
    print("gio-OS safety gate v1: PASS")


if __name__ == "__main__":
    main()
