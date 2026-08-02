from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _slug(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.lower()).strip("-")
    return slug[:48] or "objective"


@dataclass(frozen=True)
class DeliveryObjective:
    project_id: str
    repository: str
    integration_lane: str
    title: str
    acceptance: tuple[str, ...]
    collision_domains: tuple[str, ...]
    max_workers: int = 5

    def __post_init__(self) -> None:
        if not self.project_id or not self.repository or not self.title:
            raise ValueError("objective requires project_id, repository and title")
        if not self.acceptance:
            raise ValueError("objective requires acceptance criteria")
        if not self.collision_domains:
            raise ValueError("objective requires collision domains")
        if not 1 <= self.max_workers <= 5:
            raise ValueError("max_workers must be between 1 and 5")

    @property
    def fingerprint(self) -> str:
        payload = {
            "project_id": self.project_id,
            "repository": self.repository,
            "integration_lane": self.integration_lane,
            "title": self.title.strip(),
            "acceptance": sorted(set(item.strip() for item in self.acceptance)),
            "collision_domains": sorted(set(item.strip() for item in self.collision_domains)),
        }
        return hashlib.sha256(_canonical_json(payload)).hexdigest()

    @property
    def branch(self) -> str:
        return f"razzo/objective/{_slug(self.project_id)}-{self.fingerprint[:12]}"

    @property
    def pr_marker(self) -> str:
        return f"<!-- razzo-objective:{self.fingerprint} -->"


@dataclass(frozen=True)
class ObservedPullRequest:
    number: int
    branch: str
    body: str
    state: str
    head_sha: str


@dataclass(frozen=True)
class CanonicalResolution:
    action: str
    branch: str
    canonical_pr: int | None
    duplicate_prs: tuple[int, ...]


def resolve_canonical_pr(objective: DeliveryObjective, pull_requests: Iterable[ObservedPullRequest]) -> CanonicalResolution:
    matches = [
        pr for pr in pull_requests
        if pr.state == "open" and (pr.branch == objective.branch or objective.pr_marker in pr.body)
    ]
    matches.sort(key=lambda pr: pr.number, reverse=True)
    if not matches:
        return CanonicalResolution("CREATE", objective.branch, None, ())
    canonical = matches[0]
    duplicates = tuple(pr.number for pr in matches[1:])
    return CanonicalResolution(
        "BLOCK_DUPLICATES" if duplicates else "UPDATE",
        objective.branch,
        canonical.number,
        duplicates,
    )


def validate_exact_head(expected: str, observed: str) -> None:
    if not _SHA_RE.fullmatch(expected) or not _SHA_RE.fullmatch(observed):
        raise ValueError("expected and observed heads must be exact lowercase SHA-1 values")
    if expected != observed:
        raise ValueError(f"exact-head mismatch: expected {expected}, observed {observed}")


def validate_receipt(receipt: dict[str, Any], objective: DeliveryObjective, expected_head: str) -> None:
    required = {
        "objective_fingerprint", "candidate_sha", "expected_head", "tests",
        "product_ci", "robot_qa", "changed_files", "worker_count",
    }
    missing = sorted(required - receipt.keys())
    if missing:
        raise ValueError(f"receipt missing fields: {', '.join(missing)}")
    if receipt["objective_fingerprint"] != objective.fingerprint:
        raise ValueError("receipt objective fingerprint mismatch")
    validate_exact_head(expected_head, str(receipt["expected_head"]))
    validate_exact_head(str(receipt["candidate_sha"]), str(receipt["candidate_sha"]))
    if not 1 <= int(receipt["worker_count"]) <= objective.max_workers:
        raise ValueError("receipt worker count outside objective limit")
    if not receipt["changed_files"]:
        raise ValueError("receipt requires a real diff")
    if receipt["tests"] != "passed" or receipt["product_ci"] != "passed":
        raise ValueError("tests and product CI must pass")
    if receipt["robot_qa"] not in {"passed", "not_applicable_with_evidence"}:
        raise ValueError("separate Robot QA evidence is required")
