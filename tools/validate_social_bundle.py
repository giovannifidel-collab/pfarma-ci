#!/usr/bin/env python3
"""Fail-closed, isolated validation of PFarma Social's PUBLIC ciphertext envelope.

This intentionally does not replace or relax the global PFarma CI repository
policy: this shared public repo contains other independent projects. Only the
single PFarma Social encrypted artifact is within this workflow's scope.
Actual authenticity is enforced by AES-256-GCM decryption in the next step.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import sys
from pathlib import Path

MAX_BUNDLE_BYTES = 3 * 1024 * 1024
SOCIAL_BUNDLE = Path("bundle/pfarma-social.bundle.json")
FIELDS = {
    "format", "algorithm", "source_ref", "file_count", "plaintext_sha256",
    "nonce_b64", "ciphertext_b64"
}
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
SHA64 = re.compile(r"[a-f0-9]{64}\Z")


def validate_bundle(path: Path = SOCIAL_BUNDLE) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("PFarma Social ciphertext file is missing or is a symlink")
    if path.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError("Encrypted social bundle exceeds maximum allowed size")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Encrypted social bundle must be valid JSON") from exc
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        raise ValueError("Encrypted social bundle schema mismatch")
    if payload["format"] != "PFARMA_CI_BUNDLE_V2":
        raise ValueError("Unrecognized encrypted transport format")
    if payload["algorithm"] != "AES-256-GCM":
        raise ValueError("PFarma Social requires authenticated AES-256-GCM")
    if not isinstance(payload["source_ref"], str) or not SHA40.fullmatch(payload["source_ref"]):
        raise ValueError("Source commit must be a 40-digit lowercase SHA")
    if not isinstance(payload["plaintext_sha256"], str) or not SHA64.fullmatch(payload["plaintext_sha256"]):
        raise ValueError("Authenticated plaintext digest must be SHA-256")
    if type(payload["file_count"]) is not int or not (1 <= payload["file_count"] <= 2000):
        raise ValueError("Authenticated file count must be in range")
    try:
        nonce = base64.b64decode(payload["nonce_b64"], validate=True)
        ciphertext = base64.b64decode(payload["ciphertext_b64"], validate=True)
    except (TypeError, binascii.Error) as exc:
        raise ValueError("Nonce and ciphertext must be valid base64") from exc
    if len(nonce) != 12:
        raise ValueError("AES-256-GCM nonce must be exactly 12 bytes")
    if len(ciphertext) < 17:
        raise ValueError("AES-256-GCM ciphertext/tag is missing")
    if len(ciphertext) > MAX_BUNDLE_BYTES:
        raise ValueError("Ciphertext is oversized")
    return payload


def main() -> None:
    try:
        p = validate_bundle()
    except (OSError, ValueError) as exc:
        sys.exit("SOCIAL BUNDLE REJECTED: " + str(exc))
    print("PASS: social-only public ciphertext structure validated; file_count=" + str(p["file_count"]))
    print("Cryptographic authenticity is checked in the subsequent AES-GCM decryption step.")


if __name__ == "__main__":
    main()
