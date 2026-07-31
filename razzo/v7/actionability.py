from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from typing import Any

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_GENERIC = re.compile(
    r"^(advance|improve|fix|update|work on|implement)(?:\s+(?:the|this|a))?\s+[a-z0-9 _-]{0,45}$",
    re.I,
)
_COSMETIC = re.compile(
    r"\b(placeholder|wording|copy|tooltip|aria-label|tabindex|timestamp|receipt|governance)\b",
    re.I,
)
_PFARMA_ONLY = {
    "sales",
    "receiving",
    "suppliers",
    "fiscal",
    "accounting",
    "inventory",
    "catalog",
}
_FORBIDDEN_COMMAND_TOKENS = re.compile(
    r"(?:^|\s)(?:curl|wget|ssh|scp|rsync|gh\s|git\s+push|sudo|docker\s+login|npm\s+publish)(?:\s|$)",
    re.I,
)
_NONEMPTY_FIELDS = (
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
    "required_tests",
    "expected_product_effect",
    "collision_domain",
    "exact_input_sha",
    "integration_lane",
    "allowed_surfaces",
    "forbidden_surfaces",
    "risk_class",
    "evidence_required",
)
_REQUIRED_PRESENT_FIELDS = ("dependencies", "human_gate")
_ALLOWED_OUTCOMES = {
    "PRODUCT_DELIVERED",
    "PRODUCT_CHANGED_TESTS_GREEN",
    "PRODUCT_CHANGED_TESTS_FAILED",
    "PRODUCT_CHANGED_PUBLISH_FAILED",
    "NO_ACTIONABLE_CHANGE",
    "DUPLICATE",
    "COOLDOWN",
    "BLOCKED",
    "HUMAN_GATE",
    "FAILED",
    "REQUIRES_REDISCOVERY",
}


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def fingerprint(item: dict[str, Any]) -> str:
    source = item.get("issue_number") or item.get("discovery_source") or "unknown"
    payload = "|".join(
        (
            str(item.get("project_id", "")),
            str(source),
            normalize(str(item.get("product_objective", ""))),
            str(item.get("collision_domain", "")),
            str(item.get("exact_input_sha", "")),
        )
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _safe_relative_surface(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    raw = value.strip().replace("\\", "/")
    path = PurePosixPath(raw)
    return not path.is_absolute() and ".." not in path.parts and raw not in {".", "./"}


def _surface_is_allowed(target: str, allowed: list[str]) -> bool:
    normalized = target.rstrip("/")
    return any(
        normalized == candidate.rstrip("/")
        or normalized.startswith(candidate.rstrip("/") + "/")
        for candidate in allowed
        if _safe_relative_surface(candidate)
    )


def validate(
    item: dict[str, Any],
    *,
    open_pr_issue_numbers: set[int] | None = None,
    state: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    for field in _NONEMPTY_FIELDS:
        if field not in item or item[field] in (None, "", []):
            reasons.append(f"missing:{field}")
    for field in _REQUIRED_PRESENT_FIELDS:
        if field not in item:
            reasons.append(f"missing:{field}")

    if not isinstance(item.get("dependencies"), list):
        reasons.append("dependencies_not_list")
    if not isinstance(item.get("human_gate"), bool):
        reasons.append("human_gate_not_boolean")
    elif item.get("human_gate"):
        reasons.append("human_gate_required")

    objective = str(item.get("product_objective", "")).strip()
    if len(objective) < 20 or _GENERIC.fullmatch(objective):
        reasons.append("generic_objective")

    criteria = item.get("acceptance_criteria")
    if not isinstance(criteria, list) or len(
        [entry for entry in criteria if len(str(entry).strip()) >= 8]
    ) < 2:
        reasons.append("acceptance_criteria_lt_2")

    dod = str(item.get("definition_of_done", ""))
    if len(dod.strip()) < 15:
        reasons.append("definition_of_done_not_measurable")

    targets = item.get("target_surfaces")
    allowed = item.get("allowed_surfaces")
    forbidden = item.get("forbidden_surfaces")
    if not isinstance(targets, list) or not targets:
        reasons.append("target_surface_missing")
        targets = []
    if not isinstance(allowed, list) or not allowed:
        reasons.append("allowed_surface_missing")
        allowed = []
    if not isinstance(forbidden, list) or not forbidden:
        reasons.append("forbidden_surface_missing")
        forbidden = []

    if any(not _safe_relative_surface(surface) for surface in targets + allowed + forbidden):
        reasons.append("invalid_surface_path")
    if targets and allowed and any(not _surface_is_allowed(surface, allowed) for surface in targets):
        reasons.append("target_outside_allowed_surfaces")
    if targets and forbidden and any(
        _surface_is_allowed(surface, forbidden) or _surface_is_allowed(blocked, [surface])
        for surface in targets
        for blocked in forbidden
    ):
        reasons.append("target_overlaps_forbidden_surfaces")

    tests = item.get("required_tests")
    if not isinstance(tests, list) or not tests:
        reasons.append("required_test_missing")
        tests = []
    elif any(not isinstance(command, str) or not command.strip() for command in tests):
        reasons.append("invalid_required_test")
    elif any(_FORBIDDEN_COMMAND_TOKENS.search(command) for command in tests):
        reasons.append("unsafe_required_test")

    if not _SHA_RE.fullmatch(str(item.get("exact_input_sha", ""))):
        reasons.append("invalid_exact_sha")

    domain = str(item.get("collision_domain", ""))
    project_id = str(item.get("project_id", ""))
    if not domain.startswith(project_id + "/") or domain.endswith(
        ("/ui", "/issue", "/generic", "/product")
    ):
        reasons.append("generic_collision_domain")
    leaf = domain.rsplit("/", 1)[-1]
    if project_id == "project-giovanni" and leaf in _PFARMA_ONLY:
        reasons.append("project_domain_incompatible")

    effect = str(item.get("expected_product_effect", "")).strip()
    if len(effect) < 12:
        reasons.append("expected_product_effect_not_observable")
    if _COSMETIC.search(objective) and not re.search(
        r"\b(release|beta|pilot|blocker|end-to-end|measurable)\b",
        objective + " " + effect,
        re.I,
    ):
        reasons.append("cosmetic_without_measurable_delivery_effect")

    issue = item.get("issue_number")
    if open_pr_issue_numbers and isinstance(issue, int) and issue in open_pr_issue_numbers:
        reasons.append("open_pr_overlap")

    expected_fp = fingerprint(item)
    if item.get("fingerprint") != expected_fp:
        reasons.append("fingerprint_mismatch")

    state_name = "NOT_ACTIONABLE"
    if state:
        record = state.get("items", {}).get(expected_fp)
        if record:
            now = now or datetime.now(timezone.utc)
            cooldown = record.get("cooldown_until")
            if cooldown and datetime.fromisoformat(cooldown.replace("Z", "+00:00")) > now:
                reasons.append("cooldown")
                state_name = "COOLDOWN"
            if record.get("last_outcome") == "REQUIRES_REDISCOVERY":
                reasons.append("requires_rediscovery")
                state_name = "NEEDS_DEEPER_DISCOVERY"

    if not reasons:
        return "READY", []
    return state_name, list(dict.fromkeys(reasons))


def record_outcome(
    state: dict[str, Any],
    item: dict[str, Any],
    *,
    outcome: str,
    run_id: str,
    now: datetime | None = None,
    candidate_sha: str | None = None,
    pr_number: int | None = None,
    integration_state: str | None = None,
) -> dict[str, Any]:
    """Persist an operational result and enforce deterministic cooldown escalation."""
    if outcome not in _ALLOWED_OUTCOMES:
        raise ValueError(f"unsupported outcome: {outcome}")
    now = now or datetime.now(timezone.utc)
    fp = fingerprint(item)
    if item.get("fingerprint") != fp:
        raise ValueError("fingerprint mismatch")

    items = state.setdefault("items", {})
    previous = dict(items.get(fp, {}))
    attempts = int(previous.get("attempts", 0)) + 1
    repeated_no_change = int(previous.get("consecutive_no_actionable_change", 0))
    cooldown_until: str | None = None
    effective_outcome = outcome

    if outcome == "NO_ACTIONABLE_CHANGE":
        repeated_no_change += 1
        if repeated_no_change == 1:
            cooldown_until = (now + timedelta(hours=6)).isoformat().replace("+00:00", "Z")
        elif repeated_no_change == 2:
            cooldown_until = (now + timedelta(hours=24)).isoformat().replace("+00:00", "Z")
        else:
            effective_outcome = "REQUIRES_REDISCOVERY"
    else:
        repeated_no_change = 0

    source = item.get("issue_number") or item.get("discovery_source")
    record = {
        "work_item_id": item["work_item_id"],
        "project_id": item["project_id"],
        "issue_number": item.get("issue_number"),
        "discovery_source": item.get("discovery_source"),
        "source": source,
        "collision_domain": item["collision_domain"],
        "exact_input_sha": item["exact_input_sha"],
        "attempts": attempts,
        "consecutive_no_actionable_change": repeated_no_change,
        "last_run_id": str(run_id),
        "last_outcome": effective_outcome,
        "last_attempt_at": now.isoformat().replace("+00:00", "Z"),
        "cooldown_until": cooldown_until,
        "candidate_sha": candidate_sha,
        "pr_number": pr_number,
        "integration_state": integration_state
        or previous.get("integration_state")
        or "not_started",
    }
    items[fp] = record
    state["version"] = max(int(state.get("version", 1)), 1)
    state["updated_at"] = record["last_attempt_at"]
    return record


def canonical_json(item: dict[str, Any]) -> str:
    return json.dumps(item, sort_keys=True, separators=(",", ":"))
