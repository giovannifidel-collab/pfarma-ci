from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MAX_LOGICAL_WORKER_POOL = 1000
MAX_DISCOVERY_PAGES = 10
MAX_SLICES_PER_ISSUE = 4

RISK_TERMS = (
    "destructive-production", "user-data-write", "irreplaceable-data",
    "real-secrets", "real-credentials", "paid-activation", "paid-infrastructure-activation",
    "irreversible-migration", "crypto-release",
)

RISK_PATTERNS = (
    r"explicit\s+authorization\s+before\s+(?:accessing|access|mutating|mutation|writing)",
    r"(?:write|mutat(?:e|ion)|delete|repair)\s+(?:to\s+)?real\s+(?:easyfarm\s+)?data",
    r"real\s+easyfarm\s+(?:write|mutation|access)",
    r"production\s+(?:write|mutation|delete|repair)",
    r"destructive\s+(?:write|migration|operation|repair)",
)

DELIVERY_MARKERS: tuple[tuple[str, int], ...] = (
    (r"\[razzo delivery\]", 300),
    (r"\bend[- ]to[- ]end\b|\be2e\b", 180),
    (r"\bacceptance criteria\b|\bcriteri di accettazione\b", 140),
    (r"\bdefinition of done\b|\bdefinizione di done\b", 140),
    (r"\brelease blocker\b|\bblocco rilascio\b", 130),
    (r"\bbeta blocker\b|\bblocco beta\b", 120),
    (r"\bpilot blocker\b|\bblocco pilot\b", 120),
    (r"\bmilestone\b|\bmilestone di consegna\b", 100),
    (r"\buser journey\b|\bpercorso utente\b", 90),
    (r"\bcomplete flow\b|\bflusso completo\b", 90),
    (r"\bready for beta\b|\bpronto per la beta\b", 90),
)

MICRO_REFINEMENT_PATTERNS = (
    r"\bplaceholder\b",
    r"\btooltip\b",
    r"\bwording\b|\bcopy change\b|\btesto etichetta\b",
    r"\btabindex\b|\baria[- ](?:label|controls|hidden)\b",
    r"\bfocus artifact\b|\bfocus cleanup\b|\bfocus identity\b",
    r"\bnavigation control\b|\bstatus link\b",
    r"\bzero value\b|\bvalore zero\b|\bmissing marker\b",
    r"\bminor ui\b|\bmicro[- ]refinement\b",
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


def _issue_text(issue: dict[str, Any]) -> str:
    return f"{issue.get('title','')}\n{issue.get('body','')}".lower()


def delivery_score(issue: dict[str, Any]) -> int:
    text = _issue_text(issue)
    return sum(weight for pattern, weight in DELIVERY_MARKERS if re.search(pattern, text))


def is_micro_refinement(issue: dict[str, Any]) -> bool:
    text = _issue_text(issue)
    return any(re.search(pattern, text) for pattern in MICRO_REFINEMENT_PATTERNS)


def delivery_contract(issue: dict[str, Any]) -> str:
    text = _issue_text(issue)
    matched = [pattern for pattern, _ in DELIVERY_MARKERS if re.search(pattern, text)]
    if matched:
        return "Close a measurable delivery milestone or end-to-end acceptance criterion from this issue."
    return "Produce a user-visible functional increment that advances a complete flow; do not spend a worker on cosmetic-only refinement."


def issue_score(issue: dict[str, Any]) -> int:
    title = str(issue.get("title", ""))
    text = _issue_text(issue)
    outcome_score = delivery_score(issue)

    # Delivery mode is deliberately fail-closed for cosmetic micro-work. A micro issue can still
    # run when it is explicitly tied to an end-to-end milestone, acceptance criterion or release.
    if is_micro_refinement(issue) and outcome_score == 0:
        return 0

    score = outcome_score
    if "[razzo product]" in title.lower(): score += 150
    if re.search(r"\bp0\b", text): score += 100
    if "high" in text or "alta" in text: score += 60
    if "bug" in text: score += 40
    if "operator feedback" in text: score += 25
    if "usable" in text or "operational" in text: score += 20
    if "offline" in text: score += 10
    return score


def risky(issue: dict[str, Any]) -> bool:
    text = _issue_text(issue)
    if any(term in text for term in RISK_TERMS):
        return True
    return any(re.search(pattern, text) for pattern in RISK_PATTERNS)


def references_issue(pr: dict[str, Any], number: int) -> bool:
    text = f"{pr.get('title','')}\n{pr.get('body','')}"
    return bool(re.search(rf"(?<!\d)#{number}(?!\d)", text))


def _explicit_collision_domain(project_id: str, issue: dict[str, Any]) -> str | None:
    text = _issue_text(issue)
    explicit = re.search(r"collision\s+domain\s*:\s*`?([a-z0-9][a-z0-9/_-]{1,79})`?", text)
    if explicit:
        slug = explicit.group(1).strip("`/ ")[:80]
        if slug:
            return f"{project_id}/{slug}"
    module = re.search(r"(?:modulo|module)\s*:\s*([^\n\r]{2,80})", text)
    if module:
        slug = re.sub(r"[^a-z0-9]+", "-", module.group(1).strip()).strip("-")[:48]
        if slug:
            return f"{project_id}/module/{slug}"
    return None


def collision_domains(project_id: str, issue: dict[str, Any]) -> list[str]:
    """Return bounded independent product slices for one issue.

    Explicit collision-domain/module declarations remain authoritative and yield one slice.
    Otherwise high-priority product issues may fan out across distinct semantic domains already
    present in the issue text. This is conservative: no invented subtask, no duplicate domain,
    and at most MAX_SLICES_PER_ISSUE slices.
    """
    explicit = _explicit_collision_domain(project_id, issue)
    if explicit:
        return [explicit]

    text = _issue_text(issue)
    domains: list[str] = []
    for pattern, domain in DOMAIN_PATTERNS:
        if re.search(pattern, text):
            candidate = f"{project_id}/{domain}"
            if candidate not in domains:
                domains.append(candidate)
        if len(domains) >= MAX_SLICES_PER_ISSUE:
            break
    if domains:
        return domains
    return [f"{project_id}/issue-{int(issue['number'])}"]


def collision_domain(project_id: str, issue: dict[str, Any]) -> str:
    return collision_domains(project_id, issue)[0]


def slice_id(domain: str) -> str:
    slug = domain.rsplit("/", 1)[-1]
    slug = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")
    return (slug or "slice")[:40]


def slice_instruction(domain: str) -> str:
    leaf = domain.rsplit("/", 1)[-1].replace("-", " ")
    return f"Advance only the {leaf} aspect of this issue; avoid unrelated product surfaces."


def select_fairly(items: list[dict[str, Any]], requested: int, project_ids: list[str]) -> list[dict[str, Any]]:
    """Reserve one seat per enabled project with eligible work, then fill by global priority."""
    if requested <= 0:
        return []
    selected: list[dict[str, Any]] = []
    selected_keys: set[tuple[str, int, str]] = set()

    for project_id in project_ids:
        item = next((candidate for candidate in items if candidate["project_id"] == project_id), None)
        if item is None:
            continue
        key = (item["project_id"], int(item["issue_number"]), item["collision_domain"])
        selected.append(item)
        selected_keys.add(key)
        if len(selected) >= requested:
            return selected

    for item in items:
        key = (item["project_id"], int(item["issue_number"]), item["collision_domain"])
        if key in selected_keys:
            continue
        selected.append(item)
        selected_keys.add(key)
        if len(selected) >= requested:
            break
    return selected


def api(token: str, url: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def api_pages(token: str, base_url: str, max_pages: int = MAX_DISCOVERY_PAGES) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    separator = "&" if "?" in base_url else "?"
    for page in range(1, max_pages + 1):
        url = f"{base_url}{separator}per_page=100&page={page}"
        payload = api(token, url)
        if not isinstance(payload, list):
            raise RuntimeError(f"Expected list payload from {url}")
        results.extend(payload)
        if len(payload) < 100:
            break
    return results


def discover(token: str, limit: int = 3) -> list[dict[str, Any]]:
    registry = load_json(ROOT / "razzo" / "projects.json")
    state = {p["id"]: p for p in load_json(ROOT / "razzo" / "project-state.json")["projects"]}
    global_cap = max(1, int(registry.get("totalBurstSlots", limit)))
    requested = max(0, min(limit, global_cap, MAX_LOGICAL_WORKER_POOL))
    enabled_projects = [p for p in registry["projects"] if p.get("enabled")]
    project_ids = [p["id"] for p in enabled_projects]
    found: list[dict[str, Any]] = []
    for project in enabled_projects:
        pid = project["id"]
        repo = project["repository"]
        project_cap = max(1, int(project.get("burstConcurrency", requested)))
        issues = api_pages(token, f"https://api.github.com/repos/{repo}/issues?state=open&sort=updated&direction=desc")
        pulls = api_pages(token, f"https://api.github.com/repos/{repo}/pulls?state=open")
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
            for domain in collision_domains(pid, issue):
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
                    "delivery_score": delivery_score(issue),
                    "delivery_contract": delivery_contract(issue),
                    "collision_domain": domain,
                    "slice_id": slice_id(domain),
                    "work_slice": slice_instruction(domain),
                    "exact_sha": state[pid]["exactSha"],
                    "integration_lane": project.get("integrationLane", "integration/razzo"),
                    "factory_test": project.get("factoryTest", ""),
                    "factory_plan": project.get("factoryPlan", ""),
                })
                admitted += 1
                if admitted >= project_cap:
                    break
            if admitted >= project_cap:
                break
    found.sort(key=lambda x: (-x["delivery_score"], -x["priority_score"], x["project_id"], x["collision_domain"], -x["issue_number"]))
    return select_fairly(found, requested, project_ids)


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