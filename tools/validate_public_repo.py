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
    PurePosixPath("project-giovanni-source-ref.txt"),
    PurePosixPath("family-cloud-ref.txt"),
    PurePosixPath("bundle/README.md"),
    PurePosixPath("bundle/pfarma-ci.bundle.json"),
    PurePosixPath("tools/public_ci_bundle.py"),
    PurePosixPath("tools/test_public_ci_bundle.py"),
    PurePosixPath("tools/validate_public_repo.py"),
    PurePosixPath("tools/razzo_portfolio.py"),
    PurePosixPath("tools/test_razzo_portfolio.py"),
    PurePosixPath(".github/workflows/bootstrap.yml"),
    PurePosixPath(".github/workflows/run-encrypted-pfarma.yml"),
    PurePosixPath(".github/workflows/private-source-ref-ci.yml"),
    PurePosixPath(".github/workflows/poll-private-main.yml"),
    PurePosixPath(".github/workflows/receipt-readiness-contract.yml"),
    PurePosixPath(".github/workflows/receipt-evidence-id-contract.yml"),
    PurePosixPath(".github/workflows/sales-json-contract.yml"),
    PurePosixPath(".github/workflows/product-snapshot-json-contract.yml"),
    PurePosixPath(".github/workflows/supplier-decision-json-contract.yml"),
    PurePosixPath(".github/workflows/reorder-draft-json-contract.yml"),
    PurePosixPath(".github/workflows/reorder-approval-json-contract.yml"),
    PurePosixPath(".github/workflows/reorder-submission-intent-json-contract.yml"),
    PurePosixPath(".github/workflows/reorder-readiness-json-contract.yml"),
    PurePosixPath(".github/workflows/reorder-preflight-json-contract.yml"),
    PurePosixPath(".github/workflows/project-giovanni-private-source-hosted-ci.yml"),
    PurePosixPath(".github/workflows/family-cloud-private-source-ci.yml"),
    PurePosixPath(".github/workflows/family-cloud-exact-ref-gate.yml"),
    PurePosixPath(".github/workflows/pfarma-razzo-executor-ci.yml"),
    PurePosixPath(".github/workflows/razzo-exact-ref-gates.yml"),
    PurePosixPath(".github/workflows/razzo-pfarma-product-workstreams.yml"),
    PurePosixPath(".github/workflows/razzo-portfolio-ci.yml"),
    PurePosixPath(".github/workflows/razzo-project-product-workstreams.yml"),
    PurePosixPath(".github/workflows/razzo-operational-fanout.yml"),
    PurePosixPath(".github/workflows/operator-robot-link-diagnostic.yml"),
    PurePosixPath(".github/workflows/operator-robot-sale-diagnostic.yml"),
    PurePosixPath(".github/workflows/razzo-v6-operational-factory.yml"),
    PurePosixPath(".github/workflows/razzo-v7-elastic-autoscaler.yml"),
    PurePosixPath(".github/workflows/razzo-v7-elastic-fabric.yml"),
    PurePosixPath(".github/workflows/razzo-v7-product-worker-fabric.yml"),
    PurePosixPath(".github/workflows/razzo-v7-autonomous-product-trigger.yml"),
    PurePosixPath(".github/workflows/razzo-v7-event-driven-continuation.yml"),
    PurePosixPath(".github/workflows/super-factory-discovery.yml"),
    PurePosixPath(".github/photo-ai/preparatore-v2.prompt.md"),
    PurePosixPath(".github/photo-ai/preparatore-v2.schema.json"),
    PurePosixPath(".github/workflows/project-giovanni-photo-ai.yml"),
    PurePosixPath(".github/workflows/project-giovanni-photo-ai-smoke.yml"),
    PurePosixPath("scripts/cleanup-preparatore-v2-jobs.mjs"),
    PurePosixPath("scripts/codex-auth-state.mjs"),
    PurePosixPath("scripts/preparatore-v2-job.mjs"),
    PurePosixPath("scripts/resolve-preparatore-v2-user.mjs"),
    PurePosixPath("scripts/preparatore-v2-strategic-smoke.mjs"),
    PurePosixPath("razzo/__init__.py"),
    PurePosixPath("razzo/super-factory.json"),
    PurePosixPath("razzo/super_factory/__init__.py"),
    PurePosixPath("razzo/super_factory/allocator.py"),
    PurePosixPath("razzo/super_factory/test_allocator.py"),
    PurePosixPath("razzo/pfarma-accounting-ref.txt"),
    PurePosixPath("razzo/pfarma-migration-ref.txt"),
    PurePosixPath("razzo/pfarma-ref.txt"),
    PurePosixPath("razzo/pfarma-supplier-ref.txt"),
    PurePosixPath("razzo/project-giovanni-ref.txt"),
    PurePosixPath("razzo/project-history-ref.txt"),
    PurePosixPath("razzo/project-offline-ref.txt"),
    PurePosixPath("razzo/projects.json"),
    PurePosixPath("razzo/project-state.json"),
    PurePosixPath("razzo/protocol.json"),
    PurePosixPath("razzo/UNIVERSAL_COMMAND.md"),
    PurePosixPath("razzo/v6/runtime.py"),
    PurePosixPath("razzo/v6/test_runtime.py"),
    PurePosixPath("razzo/v7/autoscaler.py"),
    PurePosixPath("razzo/v7/test_autoscaler.py"),
    PurePosixPath("razzo/v7/fabric.py"),
    PurePosixPath("razzo/v7/test_fabric.py"),
    PurePosixPath("razzo/v7/product_discovery.py"),
    PurePosixPath("razzo/v7/test_product_discovery.py"),
    PurePosixPath("razzo/v7/provider_capacity.py"),
    PurePosixPath("razzo/v7/test_provider_capacity.py"),
    PurePosixPath("razzo/v7/dispatcher_pool.py"),
    PurePosixPath("razzo/v7/test_dispatcher_pool.py"),
    PurePosixPath("razzo/v7/README-1000-pool.md"),
    PurePosixPath("razzo/v7/worker-pool-config.json"),
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
REF_FILES = (
    "source-ref.txt",
    "project-giovanni-source-ref.txt",
    "family-cloud-ref.txt",
    "razzo/pfarma-accounting-ref.txt",
    "razzo/pfarma-migration-ref.txt",
    "razzo/pfarma-ref.txt",
    "razzo/pfarma-supplier-ref.txt",
    "razzo/project-giovanni-ref.txt",
    "razzo/project-history-ref.txt",
    "razzo/project-offline-ref.txt",
)


def _validate_ref_file(filename: str) -> None:
    ref_file = ROOT / filename
    if not ref_file.exists():
        return
    value = ref_file.read_text(encoding="ascii").strip()
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise SystemExit(f"{filename} must contain exactly one lowercase 40-character commit SHA.")


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

    for filename in REF_FILES:
        _validate_ref_file(filename)

    print(f"PASS: public repository allowlist contains {len(files)} approved files; no plaintext source path admitted.")


if __name__ == "__main__":
    main()
