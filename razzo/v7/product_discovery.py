from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

RISK_TERMS = (
    "destructive-production", "user-data-write", "irreplaceable-data",
    "real-secrets", "real-credentials", "paid-activation", "paid-infrastructure-activation",
    "irreversible-migration", "crypto-release",
)

DOMAIN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(catalog|catalogo|mins[a-z]*|ean|product|prodott)", "catalog"),
    (r"\b(sales|sale|vendit|pos|cassa)", "sales"),
    (r"\b(inventory|stock|giacenz|magazzin|lot|expiry|scadenz)", "inventory"),
    (r"\b(receiv|ricezion|carico merce|goods receipt)", "receiving"),
    (r"\b(supplier|fornitor|reorder|riordin)", "suppliers"),
    (r"\b(account|contabil|invoice|fattur)", "accounting"),
    (r"\b(fiscal|epson|rt\b)", "fiscal"),
    (r"\b(photo|foto|image|immagin)", "photo-ai"),
    (r"\b(workout|allenament|scheda|trainer|preparatore)", "workout"),
    (r"\b(history|storico|progress)", "history"),
    (r"\b(offline|pwa|service worker|sync)", "offline"),
    (r"\b(dashboard|ui|ux|navigation|navigaz|sidebar)", "ui"),
    (r"\b(security|sicurezza|auth|rls)", "security"),
    (r"\b(performance|latency|throughput|prestaz)", "performance"),
    (r"\b(storage|repair|chunk|vault)", "storage"),
    (r"\b(sharing|album|timeline)", "sharing"),
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def issue_score(issue: dict[str, Any]) -> int:
    text = f"{issue.get('title','')}\n{issue.get('body','')}".lower()
    score = 0
    if re.search(r"\bp0\b", text): score += 100
    if "high" in text or "alta" in text: score += 60
    if "bug" in text: score += 40
    if "operator feedback" in text: score += 25
    if "usable" in text or "operational" in text: score += 20
    if "offline" in text: score += 10
    return score


def risky(issue: dict[str, Any]) -> bool:
    text = f"{issue.get('title','')}\n{issue.get('body','')}".lower()
    return any(term in text for term in RISK_TERMS)


def references_issue(pr: dict[str, Any], number: int) -> bool:
    text = f"{pr.get('title','')}\n{pr.get('body','')}"
    return bool(re.search(rf"(?<!\d)#{number}(?!\d)", text))


def collision_domain(project_id: str, issue: dict[str, Any]) -> str:
    text = f"{issue.get('title','')}\n{issue.get('body','')}".lower()
    module = re.search(r"(?:modulo|module)\s*:\s*([^\n\r]{2,80})", text)
    if module:
        slug = re.sub(r"[^a-z0-9]+", "-", module.group(1).strip()).strip("-")[:48]
        if slug:
            return f"{project_id}/module/{slug}"
    for pattern, domain in DOMAIN_PATTERNS:
        if re.search(pattern, text):
            return f"{project_id}/{domain}"
    return f"{project_id}/issue-{int(issue['number'])}"


def api(token: str, url: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def discover(token: str, limit: int = 3) -> list[dict[str, Any]]:
    registry = load_json(ROOT / "razzo" / "projects.json")
    state = {p["id"]: p for p in load_json(ROOT / "razzo" / "project-state.json")["projects"]}
    global_cap = max(1, int(registry.get("totalBurstSlots", limit)))
    requested = max(0, min(limit, global_cap, 220))
    found: list[dict[str, Any]] = []
    for project in [p for p in registry["projects"] if p.get("enabled")]:
        pid = project["id"]
        repo = project["repository"]
        project_cap = max(1, int(project.get("burstConcurrency", requested)))
        issues = api(token, f"https://api.github.com/repos/{repo}/issues?state=open&sort=updated&direction=desc&per_page=100")
        pulls = api(token, f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=100")
        candidates: list[tuple[int, dict[str, Any]]] = []
        for issue in issues:
            if "pull_request" in issue or risky(issue):
                continue
            number = int(issue["number"])
            if any(references_issue(pr, number) for pr in pulls):
                continue
            score = issue_score(issue)
            if score <= 0:
                continue
            candidates.append((score, issue))
        candidates.sort(key=lambda pair: (-pair[0], -int(pair[1]["number"])))
        used_domains: set[str] = set()
        admitted = 0
        for score, issue in candidates:
            domain = collision_domain(pid, issue)
            if domain in used_domains:
                continue
            used_domains.add(domain)
            found.append({
                "project_id": pid,
                "repository": repo,
                "issue_number": int(issue["number"]),
                "issue_title": str(issue.get("title") or "")[:240],
                "issue_body": str(issue.get("body") or "")[:7000],
                "priority_score": score,
                "collision_domain": domain,
                "exact_sha": state[pid]["exactSha"],
                "integration_lane": project.get("integrationLane", "integration/razzo"),
                "factory_test": project.get("factoryTest", ""),
                "factory_plan": project.get("factoryPlan", ""),
            })
            admitted += 1
            if admitted >= project_cap:
                break
    found.sort(key=lambda x: (-x["priority_score"], x["project_id"], x["collision_domain"], -x["issue_number"]))
    return found[:requested]


def main() -> int:
    token = os.environ.get("PFARMA_SOURCE_TOKEN", "").strip()
    if not token:
        raise SystemExit("PFARMA_SOURCE_TOKEN is required for dynamic private product discovery")
    limit = int(os.environ.get("RAZZO_PRODUCT_WORKER_CAP", "3"))
    items = discover(token, limit=limit)
    print(json.dumps({"include": items}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
