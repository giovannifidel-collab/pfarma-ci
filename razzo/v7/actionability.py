from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_GENERIC = re.compile(r"^(advance|improve|fix|update|work on|implement)(?:\s+(?:the|this|a))?\s+[a-z0-9 _-]{0,45}$", re.I)
_COSMETIC = re.compile(r"\b(placeholder|wording|copy|tooltip|aria-label|tabindex|timestamp|receipt|governance)\b", re.I)
_PFARMA_ONLY = {"sales", "receiving", "suppliers", "fiscal", "accounting", "inventory", "catalog"}
_NONEMPTY_FIELDS = (
    "work_item_id", "fingerprint", "project_id", "repository", "product_objective",
    "user_impact", "rationale", "acceptance_criteria", "definition_of_done",
    "target_surfaces", "required_tests", "expected_product_effect", "collision_domain",
    "exact_input_sha", "integration_lane", "allowed_surfaces", "forbidden_surfaces",
    "risk_class", "evidence_required",
)
_REQUIRED_PRESENT_FIELDS = ("dependencies", "human_gate")


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def fingerprint(item: dict[str, Any]) -> str:
    source = item.get("issue_number") or item.get("discovery_source") or "unknown"
    payload = "|".join((
        str(item.get("project_id", "")), str(source), normalize(str(item.get("product_objective", ""))),
        str(item.get("collision_domain", "")), str(item.get("exact_input_sha", "")),
    ))
    return hashlib.sha256(payload.encode()).hexdigest()


def validate(item: dict[str, Any], *, open_pr_issue_numbers: set[int] | None = None,
             state: dict[str, Any] | None = None, now: datetime | None = None) -> tuple[str, list[str]]:
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
    objective = str(item.get("product_objective", "")).strip()
    if len(objective) < 20 or _GENERIC.fullmatch(objective):
        reasons.append("generic_objective")
    criteria = item.get("acceptance_criteria")
    if not isinstance(criteria, list) or len([x for x in criteria if len(str(x).strip()) >= 8]) < 2:
        reasons.append("acceptance_criteria_lt_2")
    dod = str(item.get("definition_of_done", ""))
    if len(dod.strip()) < 15:
        reasons.append("definition_of_done_not_measurable")
    if not isinstance(item.get("target_surfaces"), list) or not item.get("target_surfaces"):
        reasons.append("target_surface_missing")
    if not isinstance(item.get("required_tests"), list) or not item.get("required_tests"):
        reasons.append("required_test_missing")
    if not _SHA_RE.fullmatch(str(item.get("exact_input_sha", ""))):
        reasons.append("invalid_exact_sha")
    domain = str(item.get("collision_domain", ""))
    project_id = str(item.get("project_id", ""))
    if not domain.startswith(project_id + "/") or domain.endswith(("/ui", "/issue", "/generic", "/product")):
        reasons.append("generic_collision_domain")
    leaf = domain.rsplit("/", 1)[-1]
    if project_id == "project-giovanni" and leaf in _PFARMA_ONLY:
        reasons.append("project_domain_incompatible")
    effect = str(item.get("expected_product_effect", "")).strip()
    if len(effect) < 12:
        reasons.append("expected_product_effect_not_observable")
    if _COSMETIC.search(objective) and not re.search(r"\b(release|beta|pilot|blocker|end-to-end|measurable)\b", objective + " " + effect, re.I):
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
    return state_name, reasons


def canonical_json(item: dict[str, Any]) -> str:
    return json.dumps(item, sort_keys=True, separators=(",", ":"))
