from __future__ import annotations

import hashlib
import json
import posixpath
import re
from typing import Any

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_GENERIC_OBJECTIVE_RE = re.compile(
    r"^(advance|improve|fix|update|work on|implement)(?:\s+(?:the|this|a))?\s+[a-z0-9 _-]{0,45}$",
    re.IGNORECASE,
)
_FORBIDDEN_PREFIXES = (
    ".github/",
    "infra/",
    "migrations/",
    "secrets/",
    "factory/policy",
    "factory/task-graph",
    "factory/task_graph",
)
_REQUIRED_NONEMPTY = (
    "work_item_id",
    "fingerprint",
    "project_id",
    "repository",
    "product_objective",
    "user_impact",
    "rationale",
    "acceptance_criteria",
    "definition_of_done",
    "target_surfaces",
    "expected_product_effect",
    "collision_domain",
    "exact_input_sha",
    "integration_lane",
    "allowed_surfaces",
    "evidence_required",
)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def fingerprint(item: dict[str, Any]) -> str:
    source = item.get("issue_number") or item.get("discovery_source") or "unknown"
    payload = "|".join(
        (
            str(item.get("project_id", "")),
            str(source),
            normalize_text(str(item.get("product_objective", ""))),
            str(item.get("collision_domain", "")),
            str(item.get("exact_input_sha", "")),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_relative_path(value: str) -> bool:
    path = value.strip().replace("\\", "/")
    if not path or path.startswith("/") or path.startswith("~"):
        return False
    normalized = posixpath.normpath(path)
    if normalized == ".." or normalized.startswith("../"):
        return False
    return not normalized.startswith(_FORBIDDEN_PREFIXES)


def validate(item: dict[str, Any], *, open_pr_issue_numbers: set[int] | None = None) -> tuple[str, list[str]]:
    reasons: list[str] = []

    for field in _REQUIRED_NONEMPTY:
        if item.get(field) in (None, "", []):
            reasons.append(f"missing:{field}")

    objective = str(item.get("product_objective", "")).strip()
    if len(objective) < 20 or _GENERIC_OBJECTIVE_RE.fullmatch(objective):
        reasons.append("generic_objective")

    criteria = item.get("acceptance_criteria")
    if not isinstance(criteria, list) or len([x for x in criteria if len(str(x).strip()) >= 8]) < 2:
        reasons.append("acceptance_criteria_lt_2")

    if len(str(item.get("definition_of_done", "")).strip()) < 20:
        reasons.append("definition_of_done_not_measurable")

    target_surfaces = item.get("target_surfaces")
    if not isinstance(target_surfaces, list) or not target_surfaces:
        reasons.append("target_surfaces_missing")
    elif any(not _safe_relative_path(str(path)) for path in target_surfaces):
        reasons.append("unsafe_target_surface")

    allowed_surfaces = item.get("allowed_surfaces")
    if not isinstance(allowed_surfaces, list) or not allowed_surfaces:
        reasons.append("allowed_surfaces_missing")
    elif any(not _safe_relative_path(str(path)) for path in allowed_surfaces):
        reasons.append("unsafe_allowed_surface")

    if not _SHA_RE.fullmatch(str(item.get("exact_input_sha", ""))):
        reasons.append("invalid_exact_sha")

    project_id = str(item.get("project_id", ""))
    domain = str(item.get("collision_domain", ""))
    if not domain.startswith(project_id + "/"):
        reasons.append("collision_domain_wrong_project")
    if domain.endswith(("/ui", "/generic", "/product", "/issue")):
        reasons.append("generic_collision_domain")

    if len(str(item.get("expected_product_effect", "")).strip()) < 15:
        reasons.append("expected_product_effect_not_observable")

    issue_number = item.get("issue_number")
    if open_pr_issue_numbers and isinstance(issue_number, int) and issue_number in open_pr_issue_numbers:
        reasons.append("open_pr_overlap")

    if item.get("fingerprint") != fingerprint(item):
        reasons.append("fingerprint_mismatch")

    if item.get("human_gate") not in (False, None):
        reasons.append("human_gate_required")

    return ("READY", []) if not reasons else ("NOT_ACTIONABLE", reasons)


def canonical_json(item: dict[str, Any]) -> str:
    return json.dumps(item, sort_keys=True, separators=(",", ":"))
