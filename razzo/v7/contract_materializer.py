from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from razzo.v7.actionability import fingerprint, validate

FORBIDDEN_SURFACES = [
    ".github/workflows",
    "infra",
    "migrations",
    "secrets",
    "factory/policy",
    "factory/task-graph.json",
    "factory/task_graph.json",
]
MAX_CANDIDATES_PER_PROJECT = 3


def extract_json_payload(text: str) -> Any:
    """Extract one JSON object/list from bounded model output."""
    stripped = text.strip()
    candidates = [stripped]
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", stripped, flags=re.I | re.S)
    candidates.extend(reversed(fenced))
    starts = [index for index, char in enumerate(stripped) if char in "[{"]
    for start in starts:
        for end in range(len(stripped), start, -1):
            fragment = stripped[start:end].strip()
            if fragment and fragment[-1:] in "]}":
                candidates.append(fragment)
                break
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
    raise ValueError("discovery output did not contain valid JSON")


def candidate_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("candidates", [])
    if not isinstance(payload, list):
        raise ValueError("discovery JSON must be a list or {'candidates': [...]} object")
    return [entry for entry in payload if isinstance(entry, dict)][:MAX_CANDIDATES_PER_PROJECT]


def tracked_files(product_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(product_root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return [part.decode("utf-8") for part in result.stdout.split(b"\0") if part]


def surface_matches(surface: str, files: list[str]) -> bool:
    rule = surface.strip().replace("\\", "/").lstrip("./").rstrip("/")
    if not rule:
        return False
    if any(token in rule for token in "*?["):
        return any(fnmatch.fnmatch(path, rule) for path in files)
    return any(path == rule or path.startswith(rule + "/") for path in files)


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(entry).strip() for entry in value if str(entry).strip()]


def materialize(
    raw_text: str,
    *,
    project: dict[str, Any],
    exact_sha: str,
    issue_number: int,
    issue_title: str,
    product_root: Path,
) -> dict[str, Any]:
    payload = extract_json_payload(raw_text)
    candidates = candidate_list(payload)
    files = tracked_files(product_root)
    ready: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    used_domains: set[str] = set()
    used_objectives: set[str] = set()

    trusted_tests = [
        command.strip()
        for command in (project.get("factoryTest", ""), project.get("factoryPlan", ""))
        if isinstance(command, str) and command.strip()
    ]
    project_id = str(project["id"])

    for index, candidate in enumerate(candidates, start=1):
        candidate_id = str(candidate.get("candidate_id") or f"candidate-{index}")
        reasons: list[str] = []
        targets = _strings(candidate.get("target_surfaces"))
        evidence = _strings(candidate.get("evidence_required"))
        criteria = _strings(candidate.get("acceptance_criteria"))
        dependencies = _strings(candidate.get("dependencies"))

        if candidate.get("human_gate") not in (None, False):
            reasons.append("human_gate_required")
        if any(bool(candidate.get(key)) for key in (
            "production_write",
            "destructive_operation",
            "paid_infrastructure",
            "real_data_access",
            "secret_access",
        )):
            reasons.append("unsafe_candidate_capability")
        if not targets or any(not surface_matches(surface, files) for surface in targets):
            reasons.append("target_surface_not_verified_in_exact_checkout")

        domain = str(candidate.get("collision_domain") or "").strip().strip("/")
        if domain and not domain.startswith(project_id + "/"):
            domain = f"{project_id}/{domain}"
        if not re.fullmatch(r"[a-z0-9][a-z0-9/_-]{2,120}", domain):
            reasons.append("invalid_collision_domain")
        objective = str(candidate.get("product_objective") or "").strip()
        normalized_objective = re.sub(r"\s+", " ", objective.lower())

        if domain in used_domains:
            reasons.append("duplicate_collision_domain_in_discovery")
        if normalized_objective in used_objectives:
            reasons.append("duplicate_objective_in_discovery")

        item: dict[str, Any] = {
            "work_item_id": f"{project_id}-issue-{issue_number}-{index:02d}",
            "fingerprint": "",
            "project_id": project_id,
            "repository": project["repository"],
            "issue_number": int(issue_number),
            "discovery_source": f"codex-read-only:{issue_number}:{candidate_id}",
            "product_objective": objective,
            "user_impact": str(candidate.get("user_impact") or "").strip(),
            "rationale": str(candidate.get("rationale") or "").strip(),
            "acceptance_criteria": criteria,
            "definition_of_done": str(candidate.get("definition_of_done") or "").strip(),
            "target_surfaces": targets,
            "required_tests": trusted_tests,
            "expected_product_effect": str(candidate.get("expected_product_effect") or "").strip(),
            "collision_domain": domain,
            "exact_input_sha": exact_sha,
            "integration_lane": project.get("integrationLane", "integration/razzo"),
            "allowed_surfaces": targets,
            "forbidden_surfaces": list(FORBIDDEN_SURFACES),
            "dependencies": dependencies,
            "risk_class": "safe-product",
            "human_gate": False,
            "evidence_required": evidence,
            "factory_test": project.get("factoryTest", ""),
            "factory_plan": project.get("factoryPlan", ""),
            "issue_title": issue_title[:240],
            "actionability_state": "PENDING",
        }
        item["fingerprint"] = fingerprint(item)
        state, validation_reasons = validate(item)
        reasons.extend(validation_reasons)

        if reasons:
            rejected.append({
                "project_id": project_id,
                "issue_number": issue_number,
                "candidate_id": candidate_id,
                "state": "NOT_ACTIONABLE",
                "reasons": list(dict.fromkeys(reasons)),
            })
            continue

        item["actionability_state"] = state
        ready.append(item)
        used_domains.add(domain)
        used_objectives.add(normalized_objective)

    return {
        "project_id": project_id,
        "repository": project["repository"],
        "issue_number": issue_number,
        "exact_input_sha": exact_sha,
        "ready": ready,
        "rejected": rejected,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-output", required=True)
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--exact-sha", required=True)
    parser.add_argument("--issue-number", required=True, type=int)
    parser.add_argument("--issue-title", required=True)
    parser.add_argument("--product-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = materialize(
        Path(args.raw_output).read_text(encoding="utf-8"),
        project=json.loads(args.project_json),
        exact_sha=args.exact_sha,
        issue_number=args.issue_number,
        issue_title=args.issue_title,
        product_root=Path(args.product_root),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "project_id": result["project_id"],
        "ready": len(result["ready"]),
        "rejected": len(result["rejected"]),
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
