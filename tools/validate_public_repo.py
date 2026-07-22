#!/usr/bin/env python3
"""Fail closed if plaintext PFarma-like files are accidentally added to pfarma-ci."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_EXACT = {
    PurePosixPath("README.md"),
    PurePosixPath("SECURITY.md"),
    PurePosixPath("source-ref.txt"),
    PurePosixPath("bundle/README.md"),
    PurePosixPath("bundle/pfarma-ci.bundle.json"),
    PurePosixPath("tools/public_ci_bundle.py"),
    PurePosixPath("tools/test_public_ci_bundle.py"),
    PurePosixPath("tools/validate_public_repo.py"),
    PurePosixPath(".github/workflows/bootstrap.yml"),
    PurePosixPath(".github/workflows/run-encrypted-pfarma.yml"),
    PurePosixPath(".github/workflows/private-source-ref-ci.yml"),
    PurePosixPath(".github/workflows/poll-private-main.yml"),
    PurePosixPath(".github/workflows/receipt-readiness-contract.yml"),
    PurePosixPath(".github/workflows/receipt-evidence-id-contract.yml"),
    PurePosixPath(".github/workflows/sales-json-contract.yml"),
    PurePosixPath(".github/workflows/product-snapshot-json-contract.yml"),
    PurePosixPath(".github/workflows/supplier-decision-json-contract.yml"),
}
IGNORED_ROOTS = {".git"}
BUNDLE_REQUIRED_FIELDS = {
    "format",
    "algorithm",
    "source_ref",
    "file_count",
    "plaintext_sha256",
    "nonce_b64",
    "ciphertext_b64",
}


def main() -> None:
    files: list[PurePosixPath] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = PurePosixPath(path.relative_to(ROOT).as_posix())
        if rel.parts and rel.parts[0] in IGNORED_ROOTS:
            continue
        files.append(rel)

    unexpected = sorted(str(path) for path in files if path not in ALLOWED_EXACT)
    if unexpected:
        raise SystemExit("Unexpected public-repository files rejected: " + ", ".join(unexpected))

    bundle = ROOT / "bundle" / "pfarma-ci.bundle.json"
    if bundle.exists():
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

    source_ref = ROOT / "source-ref.txt"
    if source_ref.exists():
        value = source_ref.read_text(encoding="ascii").strip()
        if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
            raise SystemExit("source-ref.txt must contain exactly one lowercase 40-character commit SHA.")

    print(f"PASS: public repository allowlist contains {len(files)} approved files; no plaintext source path admitted.")


if __name__ == "__main__":
    main()
