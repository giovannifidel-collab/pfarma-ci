#!/usr/bin/env python3
"""Fail closed if private product source or sensitive runtime evidence enters pfarma-ci."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
IGNORED_ROOTS = {".git"}

ALLOWED_TOP_LEVEL = {
    PurePosixPath("README.md"),
    PurePosixPath("SECURITY.md"),
    PurePosixPath("source-ref.txt"),
    PurePosixPath("project-giovanni-source-ref.txt"),
    PurePosixPath("family-cloud-ref.txt"),
}

ALLOWED_EXACT = {
    PurePosixPath("bundle/README.md"),
    PurePosixPath("bundle/pfarma-ci.bundle.json"),
    PurePosixPath("razzo/__init__.py"),
    PurePosixPath("razzo/super-factory.json"),
    PurePosixPath("razzo/projects.json"),
    PurePosixPath("razzo/project-state.json"),
    PurePosixPath("razzo/protocol.json"),
    PurePosixPath("razzo/UNIVERSAL_COMMAND.md"),
    PurePosixPath("razzo/pfarma-accounting-ref.txt"),
    PurePosixPath("razzo/pfarma-migration-ref.txt"),
    PurePosixPath("razzo/pfarma-ref.txt"),
    PurePosixPath("razzo/pfarma-supplier-ref.txt"),
    PurePosixPath("razzo/project-giovanni-ref.txt"),
    PurePosixPath("razzo/project-history-ref.txt"),
    PurePosixPath("razzo/project-offline-ref.txt"),
    PurePosixPath("razzo/state/README.md"),
    PurePosixPath("razzo/runtime_v6/bin/git"),
    PurePosixPath("tests/test_razzo_runtime_v6.py"),
}

ALLOWED_CODE_PREFIXES = (
    PurePosixPath("tools"),
    PurePosixPath("scripts"),
    PurePosixPath("razzo/super_factory"),
    PurePosixPath("razzo/v6"),
    PurePosixPath("razzo/v7"),
    PurePosixPath("razzo/runtime_v6"),
    PurePosixPath("razzo/public_fabric"),
    PurePosixPath("razzo/kernel"),
    PurePosixPath("razzo/audits"),
)

RUNTIME_JSON_PREFIXES = (
    PurePosixPath("receipts"),
    PurePosixPath("razzo/receipts"),
    PurePosixPath("razzo/runtime-receipts"),
    PurePosixPath("razzo/runtime-diagnostics"),
    PurePosixPath("razzo/runtime-preflight"),
    PurePosixPath("razzo/state"),
)

BUNDLE_REQUIRED_FIELDS = {
    "format", "algorithm", "source_ref", "file_count", "plaintext_sha256", "nonce_b64", "ciphertext_b64",
}
REF_FILES = (
    "source-ref.txt", "project-giovanni-source-ref.txt", "family-cloud-ref.txt",
    "razzo/pfarma-accounting-ref.txt", "razzo/pfarma-migration-ref.txt", "razzo/pfarma-ref.txt",
    "razzo/pfarma-supplier-ref.txt", "razzo/project-giovanni-ref.txt", "razzo/project-history-ref.txt",
    "razzo/project-offline-ref.txt",
)
FORBIDDEN_KEYS = {
    "token", "secret", "password", "credential", "authorization", "cookie", "private_key", "api_key",
    "access_token", "refresh_token", "client_secret",
}


def _under(rel: PurePosixPath, prefix: PurePosixPath) -> bool:
    return rel == prefix or prefix in rel.parents


def _validate_ref_file(filename: str) -> None:
    path = ROOT / filename
    if not path.exists():
        return
    value = path.read_text(encoding="ascii").strip()
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise SystemExit(f"{filename} must contain exactly one lowercase 40-character commit SHA.")


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).strip().lower() in FORBIDDEN_KEYS or _contains_forbidden_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(child) for child in value)
    return False


def _valid_sanitized_json(rel: PurePosixPath) -> bool:
    if rel.suffix != ".json" or not any(_under(rel, prefix) for prefix in RUNTIME_JSON_PREFIXES):
        return False
    try:
        payload = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Public runtime evidence must be valid JSON: {rel}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Public runtime evidence must be a JSON object: {rel}")
    if _contains_forbidden_key(payload):
        raise SystemExit(f"Public runtime evidence contains a forbidden sensitive key: {rel}")
    return True


def _allowed(rel: PurePosixPath) -> bool:
    if rel in ALLOWED_TOP_LEVEL or rel in ALLOWED_EXACT:
        return True
    if rel.parts[:2] == (".github", "workflows") and rel.suffix in {".yml", ".yaml"}:
        return True
    if rel.parts[:2] == (".github", "photo-ai") and rel.suffix in {".md", ".json"}:
        return True
    if any(_under(rel, prefix) for prefix in ALLOWED_CODE_PREFIXES):
        return rel.suffix in {".py", ".ps1", ".mjs", ".md", ".json", ".yml", ".yaml"}
    return _valid_sanitized_json(rel)


def _validate_bundle() -> None:
    bundle = ROOT / "bundle" / "pfarma-ci.bundle.json"
    if not bundle.exists():
        return
    try:
        payload = json.loads(bundle.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit("Encrypted bundle must be valid JSON.") from exc
    if not isinstance(payload, dict) or set(payload) != BUNDLE_REQUIRED_FIELDS:
        raise SystemExit("Encrypted bundle schema mismatch.")
    if payload.get("format") != "PFARMA_CI_BUNDLE_V2" or payload.get("algorithm") != "AES-256-GCM":
        raise SystemExit("Encrypted bundle must use the approved authenticated format.")
    if not isinstance(payload.get("ciphertext_b64"), str) or not payload["ciphertext_b64"]:
        raise SystemExit("Encrypted bundle has no ciphertext.")


def main() -> None:
    files: list[PurePosixPath] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = PurePosixPath(path.relative_to(ROOT).as_posix())
        if rel.parts and rel.parts[0] in IGNORED_ROOTS:
            continue
        files.append(rel)
    unexpected = sorted(str(path) for path in files if not _allowed(path))
    if unexpected:
        raise SystemExit("Unexpected public-repository files rejected: " + ", ".join(unexpected))
    _validate_bundle()
    for filename in REF_FILES:
        _validate_ref_file(filename)
    print(f"PASS: public repository policy contains {len(files)} approved files; runtime JSON is sanitized.")


if __name__ == "__main__":
    main()
