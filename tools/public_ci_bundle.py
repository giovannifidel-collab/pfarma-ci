#!/usr/bin/env python3
"""Create and open authenticated encrypted PFarma CI source bundles.

The public repository stores only authenticated ciphertext. The 32-byte AES key
is supplied at runtime through PFARMA_CI_BUNDLE_KEY and must never be committed.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import tarfile
from pathlib import Path, PurePosixPath
from typing import Iterable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = "PFARMA_CI_BUNDLE_V2"
ALGORITHM = "AES-256-GCM"
DEFAULT_EXCLUDES = {
    ".git",
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".venv",
    "venv",
    "node_modules",
    ".next",
    "__pycache__",
    ".pytest_cache",
    "pfarma-ci.bundle.json",
}
SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore")


def _load_key() -> bytes:
    raw = os.environ.get("PFARMA_CI_BUNDLE_KEY", "").strip()
    if not raw:
        raise SystemExit("PFARMA_CI_BUNDLE_KEY is required (base64-encoded 32-byte key).")
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise SystemExit("PFARMA_CI_BUNDLE_KEY must be valid base64.") from exc
    if len(key) != 32:
        raise SystemExit("PFARMA_CI_BUNDLE_KEY must decode to exactly 32 bytes.")
    return key


def _metadata_aad(metadata: dict[str, object]) -> bytes:
    return json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _is_excluded(relative: PurePosixPath, extra_excludes: set[str]) -> bool:
    parts = set(relative.parts)
    if parts & DEFAULT_EXCLUDES:
        return True
    if parts & extra_excludes:
        return True

    name = relative.name.lower()
    if name.startswith(".env"):
        return True
    if name.endswith(SENSITIVE_SUFFIXES):
        return True
    if name in {".npmrc", ".pypirc"}:
        return True
    return False


def _iter_source_files(root: Path, extra_excludes: set[str]) -> Iterable[tuple[Path, PurePosixPath]]:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = PurePosixPath(path.relative_to(root).as_posix())
        if _is_excluded(relative, extra_excludes):
            continue
        yield path, relative


def _build_tar(root: Path, extra_excludes: set[str]) -> tuple[bytes, int]:
    buffer = io.BytesIO()
    count = 0
    with tarfile.open(fileobj=buffer, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
        for path, relative in _iter_source_files(root, extra_excludes):
            info = archive.gettarinfo(str(path), arcname=relative.as_posix())
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with path.open("rb") as handle:
                archive.addfile(info, handle)
            count += 1
    if count == 0:
        raise SystemExit("No source files selected for the CI bundle.")
    return buffer.getvalue(), count


def pack(source: Path, output: Path, source_ref: str, extra_excludes: set[str]) -> None:
    source = source.resolve()
    if not source.is_dir():
        raise SystemExit(f"Source directory does not exist: {source}")
    if not source_ref or len(source_ref) > 200:
        raise SystemExit("source_ref must be non-empty and at most 200 characters.")

    plaintext, file_count = _build_tar(source, extra_excludes)
    digest = hashlib.sha256(plaintext).hexdigest()
    metadata: dict[str, object] = {
        "format": MAGIC,
        "algorithm": ALGORITHM,
        "source_ref": source_ref,
        "file_count": file_count,
        "plaintext_sha256": digest,
    }
    nonce = os.urandom(12)
    ciphertext = AESGCM(_load_key()).encrypt(nonce, plaintext, _metadata_aad(metadata))

    payload = {
        **metadata,
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    print(f"packed {file_count} files -> {output} ({len(ciphertext)} encrypted bytes)")


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    destination = destination.resolve()
    members = archive.getmembers()
    for member in members:
        member_path = (destination / member.name).resolve()
        if destination != member_path and destination not in member_path.parents:
            raise SystemExit(f"Unsafe archive path rejected: {member.name}")
        if member.issym() or member.islnk() or member.isdev():
            raise SystemExit(f"Unsupported archive member rejected: {member.name}")
    archive.extractall(destination, members=members, filter="data")


def unpack(bundle: Path, destination: Path) -> None:
    try:
        payload = json.loads(bundle.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("Bundle is unreadable or invalid JSON.") from exc

    required = {
        "format",
        "algorithm",
        "source_ref",
        "file_count",
        "plaintext_sha256",
        "nonce_b64",
        "ciphertext_b64",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise SystemExit("Bundle schema mismatch.")
    if payload["format"] != MAGIC or payload["algorithm"] != ALGORITHM:
        raise SystemExit("Unsupported bundle format or algorithm.")
    if not isinstance(payload["source_ref"], str) or not payload["source_ref"]:
        raise SystemExit("Invalid source_ref metadata.")
    if type(payload["file_count"]) is not int or payload["file_count"] <= 0:
        raise SystemExit("Invalid file_count metadata.")
    digest_value = payload["plaintext_sha256"]
    if not isinstance(digest_value, str) or len(digest_value) != 64:
        raise SystemExit("Invalid plaintext checksum metadata.")

    metadata = {
        "format": payload["format"],
        "algorithm": payload["algorithm"],
        "source_ref": payload["source_ref"],
        "file_count": payload["file_count"],
        "plaintext_sha256": payload["plaintext_sha256"],
    }

    try:
        nonce = base64.b64decode(payload["nonce_b64"], validate=True)
        ciphertext = base64.b64decode(payload["ciphertext_b64"], validate=True)
        if len(nonce) != 12:
            raise ValueError("invalid nonce length")
        plaintext = AESGCM(_load_key()).decrypt(nonce, ciphertext, _metadata_aad(metadata))
    except Exception as exc:
        raise SystemExit("Bundle authentication/decryption failed.") from exc

    digest = hashlib.sha256(plaintext).hexdigest()
    if digest != payload["plaintext_sha256"]:
        raise SystemExit("Bundle plaintext checksum mismatch.")

    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(plaintext), mode="r:gz") as archive:
        _safe_extract(archive, destination)

    extracted_files = sum(1 for path in destination.rglob("*") if path.is_file())
    if extracted_files != payload["file_count"]:
        raise SystemExit("Extracted file count does not match authenticated metadata.")
    print(f"unpacked {extracted_files} files from {bundle} (source_ref={payload['source_ref']})")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    pack_parser = subparsers.add_parser("pack")
    pack_parser.add_argument("--source", type=Path, required=True)
    pack_parser.add_argument("--output", type=Path, required=True)
    pack_parser.add_argument("--source-ref", required=True)
    pack_parser.add_argument("--exclude", action="append", default=[])

    unpack_parser = subparsers.add_parser("unpack")
    unpack_parser.add_argument("--bundle", type=Path, required=True)
    unpack_parser.add_argument("--destination", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "pack":
        pack(args.source, args.output, args.source_ref, set(args.exclude))
    else:
        unpack(args.bundle, args.destination)


if __name__ == "__main__":
    main()
