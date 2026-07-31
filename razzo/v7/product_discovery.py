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

_UNSAFE_PATTERNS = (
    r"\bperform\s+(?:a\s+)?production\s+(?:write|delete|mutation|migration)\b",
    r"\bexecute\s+(?:a\s+)?destructive\s+(?:operation|migration|repair)\b",
    r"\baccess\s+real\s+(?:user|customer|easyfarm)\s+data\b",
    r"\buse\s+real\s+(?:secrets|credentials)\b",
    r"\bactivate\s+paid\s+infrastructure\b",
)
_SAFE_BOUNDARY_PATTERNS = (
    r"\bno\s+(?:production|real[- ]data)\s+(?:write|writes|mutation|mutations|delete|deletes|access)\b",
    r"\bwithout\s+(?:production|real[- ]data)\s+(?:write|writes|mutation|mutations|delete|deletes|access)\b",
    r"\bindependent\s+of\s+(?:destructive-production|user-data-write|irreplaceable-data)\b",
    r"\bdoes\s+not\s+(?:write|mutate|delete|access)\b",
    r"\bnon-production\b",
    r"\bread-only\b",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def api(token: str, url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def api_pages(token: str, base_url: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    separator = "&" if "?" in base_url else "?"
    for page in range(1, MAX_DISCOVERY_PAGES + 1):
        payload = api(token, f"{base_url}{separator}per_page=100&page={page}")
        if not isinstance(payload, list):
            raise RuntimeError("expected list payload")
        results.extend(payload)
        if len(payload) < 100:
            break
    return results


def issue_text(issue: dict[str, Any]) -> str:
    return f"{issue.get('title', '')}\n{issue.get('body', '')}"


def section(text: str, names: tuple[str, ...]) -> str:
    joined = "|".join(re.escape(name) for name in names)
    heading = re.search(
        rf"(?ims)^\s*#{{1,6}}\s*(?:{joined})\s*:?\s*$\n(.+?)"
        rf"(?=^\s*#{{1,6}}\s+\S|\Z)",
        text,
    )
    if heading:
        return heading.group(1).strip()
    inline = re.search(
        rf"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?(?:{joined})(?:\*\*)?\s*:\s*(.+)$",
        text,
    )
    return inline.group(1).strip() if inline else ""


def bullets(value: str) -> list[str]:
    items: list[str] = []
    for line in value.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip().strip("`")
        if cleaned:
            items.append(cleaned)
    return items


def explicit_domain(project_id: str, text: str) -> str:
    match = re.search(
        r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?collision\s+domain(?:\*\*)?\s*:\s*"
        r"`?([a-z0-9][a-z0-9/_:-]{2,120})`?",
        text,
    )
    if not match:
        match = re.search(
            r"(?ims)^\s*#{1,6}\s*collision\s+domain\s*:?\s*$\n\s*`?"
            r"([a-z0-9][a-z0-9/_:-]{2,120})`?",
            text,
        )
    if not match:
        return ""
    raw = match.group(1).strip("`/ ").replace(":", "/")
    return raw if raw.startswith(project_id + "/") else f"{project_id}/{raw}"


def contains_unsafe_action(text: str) -> bool:
    scrubbed = text.lower()
    for pattern in _SAFE_BOUNDARY_PATTERNS:
        scrubbed = re.sub(pattern, "", scrubbed, flags=re.IGNORECASE)
    return any(re.search(pattern, scrubbed, flags=re.IGNORECASE) for pattern in _UNSAFE_PATTERNS)


def references_issue(pr: dict[str, Any], issue_number: int) -> bool:
    return bool(re.search(rf"(?<!\d)#{issue_number}(?!\d)", issue_text(pr)))


def contract_from_issue(
    project: dict[str, Any],
    project_state: dict[str, Any],
    issue: dict[str, Any],
) -> dict[str, Any] | None:
    text = issue_text(issue)
    if contains_unsafe_action(text):
        return None

    project_id = str(project["id"])
    objective = section(text, ("Product objective", "Obiettivo prodotto", "Obiettivo"))
    impact = section(text, ("User impact", "Impatto utente"))
    rationale = section(text, ("Rationale", "Motivazione", "Why this matters"))
    criteria = bullets(section(text, ("Acceptance criteria", "Criteri di accettazione", "Acceptance")))
    definition_of_done = section(text, ("Definition of Done", "Definizione di Done"))
    target_surfaces = bullets(section(text, ("Target surfaces", "Superfici bersaglio", "Files")))
    expected_effect = section(text, ("Expected product effect", "Effetto prodotto atteso"))
    evidence = bullets(section(text, ("Evidence required", "Prova richiesta", "Verification")))
    collision_domain = explicit_domain(project_id, text)

    if not all(
        (
            objective,
            impact,
            rationale,
            definition_of_done,
            target_surfaces,
            expected_effect,
            evidence,
            collision_domain,
        )
    ):
        return None
    if len(criteria) < 2:
        return None

    trusted_tests = [
        command
        for command in (project.get("factoryTest", ""), project.get("factoryPlan", ""))
        if isinstance(command, str) and command.strip()
    ]
    if not trusted_tests:
        return None

    issue_number = int(issue["number"])
    item: dict[str, Any] = {
        "work_item_id": f"{project_id}-issue-{issue_number}",
        "fingerprint": "",
        "project_id": project_id,
        "repository": project["repository"],
        "issue_number": issue_number,
        "discovery_source": f"github-issue:{issue_number}",
        "product_objective": objective,
        "user_impact": impact,
        "rationale": rationale,
        "acceptance_criteria": criteria,
        "definition_of_done": definition_of_done,
        "target_surfaces": target_surfaces,
        "required_tests": trusted_tests,
        "expected_product_effect": expected_effect,
        "collision_domain": collision_domain,
        "exact_input_sha": project_state["exactSha"],
        "integration_lane": project.get("integrationLane", "integration/razzo"),
        "allowed_surfaces": target_surfaces,
        "forbidden_surfaces": [
            ".github/workflows",
            "infra",
            "migrations",
            "secrets",
            "factory/policy",
            "factory/task-graph.json",
            "factory/task_graph.json",
        ],
        "dependencies": [],
        "risk_class": "safe-product",
        "human_gate": False,
        "evidence_required": evidence,
        "factory_test": project.get("factoryTest", ""),
        "factory_plan": project.get("factoryPlan", ""),
        "issue_title": str(issue.get("title") or "")[:240],
        "actionability_state": "PENDING",
    }
    item["fingerprint"] = fingerprint(item)
    return item


def select_fairly(
    items: list[dict[str, Any]],
    limit: int,
    project_ids: list[str],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used_domains: set[str] = set()
    used_fingerprints: set[str] = set()

    def add(item: dict[str, Any]) -> bool:
        if item["collision_domain"] in used_domains or item["fingerprint"] in used_fingerprints:
            return False
        selected.append(item)
        used_domains.add(item["collision_domain"])
        used_fingerprints.add(item["fingerprint"])
        return True

    for project_id in project_ids:
        candidate = next((item for item in items if item["project_id"] == project_id), None)
        if candidate:
            add(candidate)
        if len(selected) >= limit:
            return selected

    for item in items:
        add(item)
        if len(selected) >= limit:
            break
    return selected


def discover(token: str, limit: int) -> dict[str, Any]:
    registry = load_json(ROOT / "razzo" / "projects.json")
    state_by_project = {
        entry["id"]: entry
        for entry in load_json(ROOT / "razzo" / "project-state.json")["projects"]
    }
    enabled = [project for project in registry["projects"] if project.get("enabled")]
    ready: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for project in enabled:
        project_id = str(project["id"])
        repository = str(project["repository"])
        issues = api_pages(
            token,
            f"https://api.github.com/repos/{repository}/issues?state=open&sort=updated&direction=desc",
        )
        pulls = api_pages(token, f"https://api.github.com/repos/{repository}/pulls?state=open")
        open_pr_issues = {
            int(issue["number"])
            for issue in issues
            if "pull_request" not in issue
            and any(references_issue(pr, int(issue["number"])) for pr in pulls)
        }

        for issue in issues:
            if "pull_request" in issue:
                continue
            item = contract_from_issue(project, state_by_project[project_id], issue)
            if item is None:
                rejected.append(
                    {
                        "project_id": project_id,
                        "issue_number": int(issue["number"]),
                        "state": "NOT_ACTIONABLE",
                        "reasons": ["missing_or_unsafe_explicit_contract"],
                    }
                )
                continue
            state, reasons = validate(item, open_pr_issue_numbers=open_pr_issues)
            item["actionability_state"] = state
            if state == "READY":
                ready.append(item)
            else:
                rejected.append(
                    {
                        "project_id": project_id,
                        "issue_number": item["issue_number"],
                        "fingerprint": item["fingerprint"],
                        "state": state,
                        "reasons": reasons,
                    }
                )

    ready.sort(key=lambda item: (item["project_id"], -int(item["issue_number"])))
    selected = select_fairly(ready, max(0, limit), [str(p["id"]) for p in enabled])
    return {"include": selected, "rejected": rejected}


def main() -> int:
    token = os.environ.get("PFARMA_SOURCE_TOKEN", "").strip()
    if not token:
        raise SystemExit("PFARMA_SOURCE_TOKEN is required")
    limit = max(1, min(int(os.environ.get("RAZZO_MAX_WORKERS", "3")), 12))
    print(json.dumps(discover(token, limit), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
