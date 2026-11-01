#!/usr/bin/env python3
"""Fetch the canonical private worker as AES-256-GCM ciphertext; decrypt only on a trusted public runner.

Never checkout private GitHub source; never save plaintext in the public repo.
The existing CODEX_AUTH_STATE_KEY_B64 is an HKDF input, NOT reused as source AES key.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

SALT = b"project-giovanni-bridge-source-v1/salt"
INFO = b"pfarma-ci/preparatore-plus/source-bundle/aes256gcm/v1"
BUCKET = "preparatore-v2-worker-state"
PREFIX = "worker-source"
SHA = re.compile(r"^[0-9a-f]{40}$")
UUID = re.compile(r"^[0-9a-f-]{36}$")
MAX_BUNDLE = 5 * 1024 * 1024
ROOT = Path(__file__).resolve().parent.parent


def derived_key():
    raw = base64.b64decode(os.environ["CODEX_AUTH_STATE_KEY_B64"], validate=True)
    if len(raw) != 32:
        raise RuntimeError("Invalid private bridge authentication key")
    prk = hmac.new(SALT, raw, hashlib.sha256).digest()
    return base64.b64encode(hmac.new(prk, INFO + b"\x01", hashlib.sha256).digest()).decode()


def fetch(url):
    token = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                                 "apikey": token, "Cache-Control": "no-store"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            length = int(response.headers.get("content-length") or 0)
            if length > MAX_BUNDLE:
                raise RuntimeError("Protected response exceeds size limit")
            data = response.read(MAX_BUNDLE + 1)
            if len(data) > MAX_BUNDLE:
                raise RuntimeError("Encrypted worker response exceeds size limit")
            return data
    except urllib.error.HTTPError as error:
        if error.code in (400, 404):
            return None
        raise RuntimeError(f"Protected bundle lookup failed HTTP {error.code}") from None


def object_url(path):
    return os.environ["SUPABASE_URL"].rstrip("/") + f"/storage/v1/object/{BUCKET}/{path}"


def required_sha(job_id):
    base = os.environ["SUPABASE_URL"].rstrip("/")
    value = fetch(f"{base}/rest/v1/preparatore_v2_jobs?id=eq.{job_id}&select=request_payload&limit=1")
    if not value:
        raise RuntimeError("Job not available for encrypted worker lookup")
    rows = json.loads(value)
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeError("Invalid job lookup")
    source = (rows[0].get("request_payload") or {}).get("workerSourceSha")
    if source is not None and not SHA.fullmatch(str(source)):
        raise RuntimeError("Job references an invalid source SHA")
    return source


def verified_chunks(sha, manifest):
    count = manifest.get("chunks")
    size = manifest.get("byte_length")
    digest = manifest.get("bundle_sha256")
    if (manifest.get("v") != 2 or manifest.get("source_ref") != sha
        or type(count) is not int or not 1 <= count <= 128
        or type(size) is not int or not 1 <= size <= MAX_BUNDLE
        or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
        raise RuntimeError("Invalid authenticated-source bundle manifest")
    parts = []
    total = 0
    for index in range(count):
        piece = fetch(object_url(f"{PREFIX}/chunks/{sha}/{index:03d}.json"))
        if piece is None:
            raise RuntimeError("Encrypted source chunk missing")
        record = json.loads(piece)
        if (record.get("v") != 1 or record.get("source_ref") != sha
            or record.get("index") != index):
            raise RuntimeError("Encrypted source chunk metadata mismatch")
        part = base64.b64decode(record["data_b64"], validate=True)
        total += len(part)
        if total > MAX_BUNDLE:
            raise RuntimeError("Encrypted source exceeds allowed size")
        parts.append(part)
    content = b"".join(parts)
    if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
        raise RuntimeError("Encrypted source chunks failed integrity verification")
    envelope = json.loads(content)
    if envelope.get("source_ref") != sha:
        raise RuntimeError("Authenticated encryption source revision mismatch")
    return content


def bundle_bytes(source_sha):
    for attempt in range(15):
        try:
            sha = source_sha
            if not sha:
                pointer = fetch(object_url(f"{PREFIX}/latest.json"))
                if pointer:
                    latest = json.loads(pointer)
                    if latest.get("v") == 1 and SHA.fullmatch(str(latest.get("source_ref", ""))):
                        sha = latest["source_ref"]
            if sha:
                response = fetch(object_url(f"{PREFIX}/bundles/{sha}.json"))
                if response:
                    metadata = json.loads(response)
                    content = verified_chunks(sha, metadata)
                    return sha, content
        except (urllib.error.URLError, TimeoutError):
            pass
        if attempt < 14:
            time.sleep(12)
    raise RuntimeError("SHA-pinned encrypted worker unavailable; job stays unclaimed")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    if not UUID.fullmatch(args.job_id) or args.job_id.count("-") != 4:
        raise RuntimeError("Invalid worker job id")
    sha, content = bundle_bytes(required_sha(args.job_id))
    destination = Path(args.destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError("Refusing to overwrite existing worker directory")
    with tempfile.TemporaryDirectory(prefix="gio-encrypted-worker-") as tmp:
        bundle = Path(tmp) / "worker.bundle.json"
        bundle.write_bytes(content)
        env = dict(os.environ)
        env["PFARMA_CI_BUNDLE_KEY"] = derived_key()
        subprocess.run([sys.executable, str(ROOT / "tools/public_ci_bundle.py"), "unpack",
                        "--bundle", str(bundle), "--destination", str(destination)],
                       env=env, check=True)
    mandatory = [
        "scripts/preparatore-v2-job-compatible.mjs",
        "scripts/resolve-preparatore-v2-user.mjs",
        "scripts/codex-auth-state.mjs",
        "scripts/preparatore-quality-gate.mjs",
        "lib/coachPolicyCore.mjs",
        ".github/photo-ai/preparatore-v2.prompt.md",
    ]
    for relative in mandatory:
        if not (destination / relative).is_file():
            raise RuntimeError(f"Encrypted bundle missing required runtime file: {relative}")
    print(f"Public runner verified encrypted worker source SHA={sha}; no private checkout performed")


if __name__ == "__main__":
    main()
