from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_GENERIC = re.compile(r"^(advance|improve|fix|update|work on|implement)\b.{0,40}$", re.I)
_COSMETIC = re.compile(r"\b(placeholder|wording|copy|tooltip|aria-label|tabindex|timestamp|receipt|governance)\b", re.I)
_PFARMA_ONLY = {"sales", "receiving", "suppliers", "fiscal", "accounting", "inventory"}

REQUIRED_FIELDS = (
    "work_item_id", "fingerprint", "project_id", "repository", "product_objective",
    "user_impact", "rationale", "acceptance_criteria", "definition_of_done",
    "target_surfaces", "required_tests", "expected_product_effect", "collision_domain",
    "exact_input_sha", "integration_lane", "allowed_surfaces", "forbidden_surfaces",
    "dependencies", "risk_class", "human_gate", "evidence_required",
)


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
    for field in REQUIRED_FIELDS:
        if field not in item or item[field] in (None, "", []):
            reasons.append(f"missing:{field}")
    objective = str(item.get("product_objective", ""))
    if _GENERIC.match(objective): reasons.append("generic_objective")
    criteria = item.get("acceptance_criteria")
    if not isinstance(criteria, list) or len([x for x in criteria if str(x).strip()]) < 2:
        reasons.append("acceptance_criteria_lt_2")
    if not isinstance(item.get("target_surfaces"), list) or not item.get("target_surfaces"):
        reasons.append("target_surface_missing")
    if not isinstance(item.get("required_tests"), list) or not item.get("required_tests"):
        reasons.append("required_test_missing")
    if not _SHA_RE.fullmatch(str(item.get("exact_input_sha", ""))): reasons.append("invalid_exact_sha")
    domain = str(item.get("collision_domain", ""))
    if "/" not in domain or domain.endswith(("/ui", "/issue", "/generic")): reasons.append("generic_collision_domain")
    if item.get("project_id") == "project-giovanni" and domain.rsplit("/", 1)[-1] in _PFARMA_ONLY:
        reasons.append("project_domain_incompatible")
    if _COSMETIC.search(objective) and not str(item.get("expected_product_effect", "")).strip():
        reasons.append("cosmetic_without_effect")
    issue = item.get("issue_number")
    if open_pr_issue_numbers and isinstance(issue, int) and issue in open_pr_issue_numbers:
        reasons.append("open_pr_overlap")
    expected_fp = fingerprint(item)
    if item.get("fingerprint") != expected_fp: reasons.append("fingerprint_mismatch")
    if state:
        record = state.get("items", {}).get(expected_fp)
        if record:
            now = now or datetime.now(timezone.utc)
            cooldown = record.get("cooldown_until")
            if cooldown and datetime.fromisoformat(cooldown.replace("Z", "+00:00")) > now:
                reasons.append("cooldown")
            if record.get("last_outcome") == "REQUIRES_REDISCOVERY": reasons.append("requires_rediscovery")
    return ("READY" if not reasons else "NOT_ACTIONABLE", reasons)


def canonical_json(item: dict[str, Any]) -> str:
    return json.dumps(item, sort_keys=True, separators=(",", ":"))
