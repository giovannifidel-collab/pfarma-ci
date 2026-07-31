from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def discover(project_id: str, root: Path) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    if project_id == "family-cloud":
        index = root / "web" / "index.html"
        text = index.read_text(encoding="utf-8") if index.exists() else ""
        if not (root / "web" / "manifest.webmanifest").exists() or not (root / "web" / "sw.js").exists() or "manifest.webmanifest" not in text or "serviceWorker" not in text:
            candidates.append({
                "candidate_id": "free-local-pwa",
                "product_objective": "Make the local Family Cloud shell installable and reopenable offline with a bounded same-origin application-shell cache.",
                "user_impact": "After one online load, the alpha can reopen without connectivity while preserving browser-local journey state.",
                "rationale": "The exact checkout lacks one or more local PWA elements: linked manifest, same-origin service worker, or bounded application-shell caching.",
                "acceptance_criteria": [
                    "The served page links a valid local manifest and registers a same-origin service worker.",
                    "The service worker caches only the local application shell and provides an offline navigation fallback.",
                    "No storage API response, secret, production endpoint, or external asset is cached."
                ],
                "definition_of_done": "Manifest, service worker, registration, and focused tests are present; repository tests pass with a non-empty diff.",
                "target_surfaces": ["web/index.html", "web"],
                "expected_product_effect": "Family Cloud behaves as a bounded local-first PWA.",
                "collision_domain": "product/local-pwa-offline-reopen",
                "dependencies": [],
                "evidence_required": ["focused local PWA test", "non-empty diff"],
                "human_gate": False
            })
        if not (root / "web" / "vault-identity.js").exists() or "vault-identity.js" not in text:
            candidates.append({
                "candidate_id": "free-local-vault-identity",
                "product_objective": "Give the signed-in local alpha a stable browser-local demo vault identity that survives reloads without a remote account service.",
                "user_impact": "A user reuses the same local vault identity across reloads.",
                "rationale": "The exact checkout has no dedicated local vault identity module linked from the served page.",
                "acceptance_criteria": [
                    "A stable non-secret vault identifier is generated once and stored in localStorage.",
                    "Reloading reuses the existing identifier.",
                    "Malformed identifiers are replaced without touching media data."
                ],
                "definition_of_done": "A browser-local identity module and focused tests are present; repository tests pass with a non-empty diff.",
                "target_surfaces": ["web/index.html", "web"],
                "expected_product_effect": "The local alpha has a durable demo-vault identity without production writes.",
                "collision_domain": "product/local-vault-identity",
                "dependencies": [],
                "evidence_required": ["focused vault identity test", "non-empty diff"],
                "human_gate": False
            })
    return {"engine": "deterministic-free-v1", "candidates": candidates}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--product-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = discover(args.project_id, Path(args.product_root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"engine": payload["engine"], "candidates": len(payload["candidates"])}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
