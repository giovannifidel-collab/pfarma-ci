from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

from razzo.v7.actionability import fingerprint, validate

ROOT = Path(__file__).resolve().parents[2]
MAX_DISCOVERY_PAGES = 10
RISK_TERMS = ("destructive-production", "user-data-write", "irreplaceable-data", "real-secrets", "paid-activation", "irreversible-migration")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def api(token: str, url: str) -> Any:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def api_pages(token: str, base_url: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    sep = "&" if "?" in base_url else "?"
    for page in range(1, MAX_DISCOVERY_PAGES + 1):
        payload = api(token, f"{base_url}{sep}per_page=100&page={page}")
        if not isinstance(payload, list):
            raise RuntimeError("expected list payload")
        out.extend(payload)
        if len(payload) < 100:
            break
    return out


def issue_text(issue: dict[str, Any]) -> str:
    return f"{issue.get('title','')}\n{issue.get('body','')}"


def section(text: str, names: tuple[str, ...]) -> str:
    joined = "|".join(re.escape(n) for n in names)
    match = re.search(rf"(?ims)^\s*(?:{joined})\s*:\s*(.+?)(?=^\s*[A-Za-z][A-Za-z _-]{{2,40}}\s*:|\Z)", text)
    return match.group(1).strip() if match else ""


def bullets(value: str) -> list[str]:
    lines = [re.sub(r"^\s*[-*\d.)]+\s*", "", x).strip() for x in value.splitlines()]
    return [x for x in lines if x]


def explicit_domain(project_id: str, text: str) -> str:
    match = re.search(r"(?im)^\s*collision\s+domain\s*:\s*`?([a-z0-9][a-z0-9/_-]{2,100})`?", text)
    if not match:
        return ""
    raw = match.group(1).strip("`/ ")
    return raw if raw.startswith(project_id + "/") else f"{project_id}/{raw}"


def references_issue(pr: dict[str, Any], number: int) -> bool:
    return bool(re.search(rf"(?<!\d)#{number}(?!\d)", issue_text(pr)))


def contract_from_issue(project: dict[str, Any], state: dict[str, Any], issue: dict[str, Any]) -> dict[str, Any] | None:
    text = issue_text(issue)
    lowered = text.lower()
    if any(term in lowered for term in RISK_TERMS):
        return None
    pid = project["id"]
    objective = section(text, ("Product objective", "Obiettivo prodotto"))
    impact = section(text, ("User impact", "Impatto utente"))
    rationale = section(text, ("Rationale", "Motivazione"))
    criteria = bullets(section(text, ("Acceptance criteria", "Criteri di accettazione")))
    dod = section(text, ("Definition of Done", "Definizione di Done"))
    surfaces = bullets(section(text, ("Target surfaces", "Superfici bersaglio")))
    tests = bullets(section(text, ("Required tests", "Test richiesti")))
    effect = section(text, ("Expected product effect", "Effetto prodotto atteso"))
    evidence = bullets(section(text, ("Evidence required", "Prova richiesta")))
    domain = explicit_domain(pid, text)
    # An issue is authoritative product work only when it already carries a complete,
    # verifiable contract. Keywords, labels and generic prose never create slices.
    if not all((objective, impact, rationale, dod, effect, domain, surfaces, tests, evidence)) or len(criteria) < 2:
        return None
    number = int(issue["number"])
    item: dict[str, Any] = {
        "work_item_id": f"{pid}-issue-{number}",
        "fingerprint": "",
        "project_id": pid,
        "repository": project["repository"],
        "issue_number": number,
        "discovery_source": f"github-issue:{number}",
        "product_objective": objective,
        "user_impact": impact,
        "rationale": rationale,
        "acceptance_criteria": criteria,
        "definition_of_done": dod,
        "target_surfaces": surfaces,
        "required_tests": tests,
        "expected_product_effect": effect,
        "collision_domain": domain,
        "exact_input_sha": state["exactSha"],
        "exact_sha": state["exactSha"],
        "integration_lane": project.get("integrationLane", "integration/razzo"),
        "allowed_surfaces": surfaces,
        "forbidden_surfaces": [".github/workflows", "infra", "migrations", "secrets", "factory/policy", "factory/task-graph.json", "factory/task_graph.json"],
        "dependencies": [],
        "risk_class": "safe-product",
        "human_gate": False,
        "evidence_required": evidence,
        "issue_title": str(issue.get("title") or "")[:240],
        "issue_body": str(issue.get("body") or "")[:7000],
        "factory_test": project.get("factoryTest", ""),
        "factory_plan": project.get("factoryPlan", ""),
        "priority_score": 100,
        "actionability_state": "PENDING",
    }
    item["fingerprint"] = fingerprint(item)
    return item


def select_fairly(items: list[dict[str, Any]], limit: int, enabled_ids: list[str]) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    selected: list[dict[str, Any]] = []
    used_domains: set[str] = set()
    used_fingerprints: set[str] = set()

    def take(item: dict[str, Any]) -> bool:
        if item["collision_domain"] in used_domains or item["fingerprint"] in used_fingerprints:
            return False
        selected.append(item)
        used_domains.add(item["collision_domain"])
        used_fingerprints.add(item["fingerprint"])
        return True

    for project_id in enabled_ids:
        candidate = next((x for x in items if x["project_id"] == project_id and x not in selected), None)
        if candidate:
            take(candidate)
        if len(selected) >= limit:
            return selected
    for item in items:
        if item not in selected:
            take(item)
        if len(selected) >= limit:
            break
    return selected


def discover(token: str, limit: int = 3) -> dict[str, Any]:
    registry = load_json(ROOT / "razzo" / "projects.json")
    states = {p["id"]: p for p in load_json(ROOT / "razzo" / "project-state.json")["projects"]}
    persisted = load_json(ROOT / "razzo" / "v7" / "work-item-state.json")
    enabled = [p for p in registry["projects"] if p.get("enabled")]
    ready: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for project in enabled:
        repo = project["repository"]
        issues = api_pages(token, f"https://api.github.com/repos/{repo}/issues?state=open&sort=updated&direction=desc")
        pulls = api_pages(token, f"https://api.github.com/repos/{repo}/pulls?state=open")
        open_pr_issues = {int(i["number"]) for i in issues if "pull_request" not in i and any(references_issue(pr, int(i["number"])) for pr in pulls)}
        admitted = False
        for issue in issues:
            if "pull_request" in issue:
                continue
            item = contract_from_issue(project, states[project["id"]], issue)
            if item is None:
                rejected.append({"project_id": project["id"], "issue_number": int(issue["number"]), "state": "NOT_ACTIONABLE", "reasons": ["missing_explicit_actionability_contract"]})
                continue
            actionability_state, reasons = validate(item, open_pr_issue_numbers=open_pr_issues, state=persisted)
            item["actionability_state"] = actionability_state
            if actionability_state == "READY":
                ready.append(item)
                admitted = True
            else:
                rejected.append({"project_id": project["id"], "issue_number": item["issue_number"], "fingerprint": item["fingerprint"], "state": actionability_state, "reasons": reasons})
        if not admitted:
            rejected.append({"project_id": project["id"], "discovery_source": "repository-deep-discovery", "state": "NEEDS_DEEPER_DISCOVERY", "reasons": ["no_issue_with_complete_actionability_contract"]})
    ready.sort(key=lambda x: (-int(x["priority_score"]), x["project_id"], x["issue_number"]))
    selected = select_fairly(ready, max(0, limit), [p["id"] for p in enabled])
    return {"include": selected, "rejected": rejected}


def main() -> int:
    token = os.environ.get("PFARMA_SOURCE_TOKEN", "").strip()
    if not token:
        raise SystemExit("PFARMA_SOURCE_TOKEN is required")
    print(json.dumps(discover(token, int(os.environ.get("RAZZO_PRODUCT_WORKER_CAP", "3"))), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
