from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
INFLIGHT_LEDGER = ROOT / "razzo" / "v7" / "inflight_work.json"


def candidate(*, candidate_id: str, product_objective: str, user_impact: str,
              rationale: str, acceptance_criteria: list[str], definition_of_done: str,
              target_surfaces: list[str], expected_product_effect: str,
              collision_domain: str, evidence_required: list[str]) -> dict[str, Any]:
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


def exact_sha(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def inflight_keys() -> set[tuple[str, str, str]]:
    try:
        payload = json.loads(INFLIGHT_LEDGER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {
        (str(item.get("project_id", "")), str(item.get("candidate_id", "")), str(item.get("exact_input_sha", "")))
        for item in payload.get("items", [])
        if item.get("state") == "open"
    }


def remove_inflight(project_id: str, root: Path, candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sha = exact_sha(root)
    blocked = inflight_keys()
    ready: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for item in candidates:
        key = (project_id, str(item.get("candidate_id", "")), sha)
        if key in blocked:
            suppressed.append({"candidate_id": item.get("candidate_id"), "exact_input_sha": sha, "reason": "matching_open_product_pr"})
        else:
            ready.append(item)
    return ready, suppressed


def discover_project_giovanni(root: Path) -> list[dict[str, Any]]:
    app = root / "app"
    package = root / "package.json"
    if not app.is_dir() or not package.exists():
        return []
    try:
        dependencies = json.loads(package.read_text(encoding="utf-8")).get("dependencies", {})
    except (OSError, json.JSONDecodeError):
        return []
    if "next" not in dependencies:
        return []
    items: list[dict[str, Any]] = []
    if not (app / "error.tsx").exists():
        items.append(candidate(
            candidate_id="project-global-error-recovery",
            product_objective="Add a bounded global application error recovery screen for Project Giovanni.",
            user_impact="A user receives a clear recovery action instead of an opaque broken page when a route fails.",
            rationale="The exact Next.js App Router checkout has no app/error.tsx boundary.",
            acceptance_criteria=["Unhandled route rendering errors show an Italian accessible recovery screen.", "The recovery action invokes reset without external writes."],
            definition_of_done="A client-side App Router error boundary exists and registry-controlled suites pass.",
            target_surfaces=["app/error.tsx"],
            expected_product_effect="Route rendering failures can be recovered without abandoning the session.",
            collision_domain="product/global-error-recovery",
            evidence_required=["framework-compatible error boundary", "registry-controlled tests", "non-empty diff"],
        ))
    if not (app / "loading.tsx").exists():
        items.append(candidate(
            candidate_id="project-global-loading-feedback",
            product_objective="Add accessible global loading feedback for Project Giovanni route transitions.",
            user_impact="A user sees immediate screen-reader-compatible feedback while a route is prepared.",
            rationale="The exact Next.js App Router checkout has no app/loading.tsx fallback.",
            acceptance_criteria=["Route transitions render concise Italian loading status.", "The status uses a live region and performs no external writes."],
            definition_of_done="A framework-compatible loading fallback exists and registry-controlled suites pass.",
            target_surfaces=["app/loading.tsx"],
            expected_product_effect="Route transitions provide deterministic visual and assistive feedback.",
            collision_domain="product/global-loading-feedback",
            evidence_required=["accessible loading fallback", "registry-controlled tests", "non-empty diff"],
        ))
    return items


def discover_pfarma_cloud(root: Path) -> list[dict[str, Any]]:
    if not (root / "api").is_dir() or not (root / "tests").is_dir():
        return []
    items: list[dict[str, Any]] = []
    if not (root / "api" / "stock_threshold_preview.py").exists():
        items.append(candidate(
            candidate_id="pfarma-stock-threshold-preview",
            product_objective="Add a read-only stock threshold preview that classifies urgent, low and healthy inventory without changing stock.",
            user_impact="The operator can identify products needing attention before creating any replenishment action.",
            rationale="The exact PFarma checkout has warehouse routing previews but no isolated threshold classification module.",
            acceptance_criteria=["Classification is deterministic from available, minimum and target quantities.", "The result exposes shortage and suggested replenishment while production_write and purchase_order_write remain false."],
            definition_of_done="The preview module and focused unit tests exist and the registry-controlled PFarma suites pass.",
            target_surfaces=["api/stock_threshold_preview.py", "tests/test_stock_threshold_preview.py"],
            expected_product_effect="PFarma exposes safe inventory attention signals without mutating inventory or suppliers.",
            collision_domain="inventory/stock-threshold-preview",
            evidence_required=["focused unit test", "read-only invariants", "non-empty diff"],
        ))
    if not (root / "api" / "interwarehouse_transfer_preview.py").exists():
        items.append(candidate(
            candidate_id="pfarma-interwarehouse-transfer-preview",
            product_objective="Add a read-only E-to-A or A-to-E warehouse transfer preview with post-transfer balances and no inventory write.",
            user_impact="The operator can validate a proposed internal transfer before committing any warehouse movement.",
            rationale="The exact PFarma checkout models E and A allocations but has no bounded internal transfer preview.",
            acceptance_criteria=["Only E and A warehouses are accepted and the source must have sufficient quantity.", "The preview returns post-transfer balances with production_write false."],
            definition_of_done="The transfer preview module and focused unit tests exist and registry-controlled PFarma suites pass.",
            target_surfaces=["api/interwarehouse_transfer_preview.py", "tests/test_interwarehouse_transfer_preview.py"],
            expected_product_effect="PFarma can validate internal warehouse movements without changing real stock.",
            collision_domain="inventory/interwarehouse-transfer-preview",
            evidence_required=["focused unit test", "insufficient-stock rejection", "non-empty diff"],
        ))
    return items


def discover_family_cloud(root: Path) -> list[dict[str, Any]]:
    index = root / "web" / "index.html"
    text = index.read_text(encoding="utf-8") if index.exists() else ""
    items: list[dict[str, Any]] = []
    if not (root / "web" / "manifest.webmanifest").exists() or not (root / "web" / "sw.js").exists() or "manifest.webmanifest" not in text or "serviceWorker" not in text:
        items.append(candidate(
            candidate_id="free-local-pwa",
            product_objective="Make the local Family Cloud shell installable and reopenable offline with a bounded same-origin application-shell cache.",
            user_impact="After one online load, the alpha can reopen without connectivity.",
            rationale="The exact checkout lacks one or more local PWA elements.",
            acceptance_criteria=["The page links a local manifest and registers a same-origin service worker.", "Only the local application shell is cached."],
            definition_of_done="Manifest, service worker, registration and focused tests are present.",
            target_surfaces=["web/index.html", "web"],
            expected_product_effect="Family Cloud behaves as a bounded local-first PWA.",
            collision_domain="product/local-pwa-offline-reopen",
            evidence_required=["focused local PWA test", "non-empty diff"],
        ))
    if not (root / "web" / "vault-identity.js").exists() or "vault-identity.js" not in text:
        items.append(candidate(
            candidate_id="free-local-vault-identity",
            product_objective="Give the signed-in local alpha a stable browser-local demo vault identity that survives reloads without a remote account service.",
            user_impact="A user reuses the same local vault identity across reloads.",
            rationale="The exact checkout has no dedicated local vault identity module linked from the served page.",
            acceptance_criteria=["A stable non-secret identifier is stored locally.", "Malformed identifiers are replaced without touching media data."],
            definition_of_done="A browser-local identity module and focused tests are present.",
            target_surfaces=["web/index.html", "web"],
            expected_product_effect="The local alpha has a durable demo-vault identity without production writes.",
            collision_domain="product/local-vault-identity",
            evidence_required=["focused vault identity test", "non-empty diff"],
        ))
    return items


def discover(project_id: str, root: Path) -> dict[str, Any]:
    detectors: dict[str, Callable[[Path], list[dict[str, Any]]]] = {
        "project-giovanni": discover_project_giovanni,
        "pfarma-cloud": discover_pfarma_cloud,
        "family-cloud": discover_family_cloud,
    }
    detected = detectors.get(project_id, lambda _root: [])(root)
    candidates, suppressed = remove_inflight(project_id, root, detected)
    return {"engine": "deterministic-free-v4", "candidates": candidates, "suppressed_inflight": suppressed}


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
    print(json.dumps({"engine": payload["engine"], "candidates": len(payload["candidates"]), "suppressed_inflight": len(payload["suppressed_inflight"])}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
