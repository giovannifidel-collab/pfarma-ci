from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).with_name("public_ci_bundle.py")


def run(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def main() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source"
        source.mkdir()
        (source / "app.py").write_text("print('PFarma CI proof')\n", encoding="utf-8")
        (source / ".env").write_text("SHOULD_NOT_LEAVE_PRIVATE_REPO=1\n", encoding="utf-8")
        (source / ".npmrc").write_text("//registry.example/:_authToken=secret\n", encoding="utf-8")
        (source / "nested").mkdir()
        (source / "nested" / "contract.txt").write_text("contract\n", encoding="utf-8")

        key = base64.b64encode(os.urandom(32)).decode("ascii")
        env = os.environ.copy()
        env["PFARMA_CI_BUNDLE_KEY"] = key

        bundle = root / "pfarma-ci.bundle.json"
        result = run(
            "pack",
            "--source",
            str(source),
            "--output",
            str(bundle),
            "--source-ref",
            "test-sha",
            env=env,
        )
        assert result.returncode == 0, result.stderr

        public_text = bundle.read_text(encoding="utf-8")
        assert "PFarma CI proof" not in public_text
        assert "SHOULD_NOT_LEAVE_PRIVATE_REPO" not in public_text
        assert "_authToken" not in public_text

        payload = json.loads(public_text)
        assert payload["algorithm"] == "AES-256-GCM"
        assert payload["format"] == "PFARMA_CI_BUNDLE_V2"
        assert payload["source_ref"] == "test-sha"
        assert payload["file_count"] == 2

        destination = root / "opened"
        result = run("unpack", "--bundle", str(bundle), "--destination", str(destination), env=env)
        assert result.returncode == 0, result.stderr
        assert (destination / "app.py").read_text(encoding="utf-8") == "print('PFarma CI proof')\n"
        assert (destination / "nested" / "contract.txt").read_text(encoding="utf-8") == "contract\n"
        assert not (destination / ".env").exists()
        assert not (destination / ".npmrc").exists()

        wrong_env = env.copy()
        wrong_env["PFARMA_CI_BUNDLE_KEY"] = base64.b64encode(os.urandom(32)).decode("ascii")
        failed = run("unpack", "--bundle", str(bundle), "--destination", str(root / "wrong"), env=wrong_env)
        assert failed.returncode != 0
        assert "authentication/decryption failed" in failed.stderr

        tampered_payload = dict(payload)
        tampered_payload["ciphertext_b64"] = tampered_payload["ciphertext_b64"][:-4] + "AAAA"
        tampered = root / "tampered.json"
        tampered.write_text(json.dumps(tampered_payload), encoding="utf-8")
        failed = run("unpack", "--bundle", str(tampered), "--destination", str(root / "tampered"), env=env)
        assert failed.returncode != 0

        metadata_payload = dict(payload)
        metadata_payload["source_ref"] = "forged-sha"
        metadata_tampered = root / "metadata-tampered.json"
        metadata_tampered.write_text(json.dumps(metadata_payload), encoding="utf-8")
        failed = run(
            "unpack",
            "--bundle",
            str(metadata_tampered),
            "--destination",
            str(root / "metadata-tampered"),
            env=env,
        )
        assert failed.returncode != 0
        assert "authentication/decryption failed" in failed.stderr

    print("PASS: encrypted public-CI bundle is opaque, metadata-bound, authenticated and fail-closed.")


if __name__ == "__main__":
    main()
