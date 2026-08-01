from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def candidate(
    *,
    candidate_id: str,
    product_objective: str,
    user_impact: str,
    rationale: str,
    acceptance_criteria: list[str],
    definition_of_done: str,
    target_surfaces: list[str],
    expected_product_effect: str,
    collision_domain: str,
    evidence_required: list[str],
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "product_objective": product_objective,
        "user_impact": user_impact,
        "rationale": rationale,
        "acceptance_criteria": acceptance_criteria,
        "definition_of_done": definition_of_done,
        "target_surfaces": target_surfaces,
        "expected_product_effect": expected_product_effect,
        "collision_domain": collision_domain,
        "dependencies": [],
        "evidence_required": evidence_required,
        "human_gate": False,
    }


def discover_project_giovanni(root: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    app = root / "app"
    package = root / "package.json"
    if not app.is_dir() or not package.exists():
        return candidates

    try:
        package_json = json.loads(package.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return candidates
    dependencies = package_json.get("dependencies", {})
    if "next" not in dependencies:
        return candidates

    if not (app / "error.tsx").exists():
        candidates.append(candidate(
            candidate_id="project-global-error-recovery",
            product_objective="Add a bounded global application error recovery screen for Project Giovanni.",
            user_impact="A user receives a clear recovery action instead of an opaque broken page when a route fails.",
            rationale="The exact Next.js App Router checkout has no app/error.tsx boundary.",
            acceptance_criteria=[
                "Unhandled route rendering errors show an Italian, accessible recovery screen.",
                "The recovery action invokes the framework reset callback without performing external writes.",
            ],
            definition_of_done="A client-side App Router error boundary exists at app/error.tsx and the registry-controlled suites pass with a non-empty diff.",
            target_surfaces=["app/error.tsx"],
            expected_product_effect="Project Giovanni can recover from route rendering failures without abandoning the session.",
            collision_domain="product/global-error-recovery",
            evidence_required=["framework-compatible error boundary", "registry-controlled tests", "non-empty diff"],
        ))

    if not (app / "loading.tsx").exists():
        candidates.append(candidate(
            candidate_id="project-global-loading-feedback",
            product_objective="Add accessible global loading feedback for Project Giovanni route transitions.",
            user_impact="A user sees immediate, screen-reader-compatible feedback while a route is being prepared.",
            rationale="The exact Next.js App Router checkout has no app/loading.tsx fallback.",
            acceptance_criteria=[
                "Route transitions render a concise Italian loading status.",
                "The status uses an appropriate live region and does not introduce network or production writes.",
            ],
            definition_of_done="A framework-compatible loading fallback exists at app/loading.tsx and the registry-controlled suites pass with a non-empty diff.",
            target_surfaces=["app/loading.tsx"],
            expected_product_effect="Route transitions provide deterministic visual and assistive-technology feedback.",
            collision_domain="product/global-loading-feedback",
            evidence_required=["accessible loading fallback", "registry-controlled tests", "non-empty diff"],
        ))
    return candidates


def discover_family_cloud(root: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    index = root / "web" / "index.html"
    text = index.read_text(encoding="utf-8") if index.exists() else ""
    if not (root / "web" / "manifest.webmanifest").exists() or not (root / "web" / "sw.js").exists() or "manifest.webmanifest" not in text or "serviceWorker" not in text:
        candidates.append(candidate(
            candidate_id="free-local-pwa",
            product_objective="Make the local Family Cloud shell installable and reopenable offline with a bounded same-origin application-shell cache.",
            user_impact="After one online load, the alpha can reopen without connectivity while preserving browser-local journey state.",
            rationale="The exact checkout lacks one or more local PWA elements: linked manifest, same-origin service worker, or bounded application-shell caching.",
            acceptance_criteria=[
                "The served page links a valid local manifest and registers a same-origin service worker.",
                "The service worker caches only the local application shell and provides an offline navigation fallback.",
                "No storage API response, secret, production endpoint, or external asset is cached.",
            ],
            definition_of_done="Manifest, service worker, registration, and focused tests are present; repository tests pass with a non-empty diff.",
            target_surfaces=["web/index.html", "web"],
            expected_product_effect="Family Cloud behaves as a bounded local-first PWA.",
            collision_domain="product/local-pwa-offline-reopen",
            evidence_required=["focused local PWA test", "non-empty diff"],
        ))
    if not (root / "web" / "vault-identity.js").exists() or "vault-identity.js" not in text:
        candidates.append(candidate(
            candidate_id="free-local-vault-identity",
            product_objective="Give the signed-in local alpha a stable browser-local demo vault identity that survives reloads without a remote account service.",
            user_impact="A user reuses the same local vault identity across reloads.",
            rationale="The exact checkout has no dedicated local vault identity module linked from the served page.",
            acceptance_criteria=[
                "A stable non-secret vault identifier is generated once and stored in localStorage.",
                "Reloading reuses the existing identifier.",
                "Malformed identifiers are replaced without touching media data.",
            ],
            definition_of_done="A browser-local identity module and focused tests are present; repository tests pass with a non-empty diff.",
            target_surfaces=["web/index.html", "web"],
            expected_product_effect="The local alpha has a durable demo-vault identity without production writes.",
            collision_domain="product/local-vault-identity",
            evidence_required=["focused vault identity test", "non-empty diff"],
        ))
    return candidates


def discover(project_id: str, root: Path) -> dict[str, Any]:
    detectors = {
        "project-giovanni": discover_project_giovanni,
        "family-cloud": discover_family_cloud,
    }
    detector = detectors.get(project_id)
    candidates = detector(root) if detector else []
    return {"engine": "deterministic-free-v2", "candidates": candidates}


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
