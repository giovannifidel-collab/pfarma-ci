from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be RFC3339 UTC with Z suffix")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("timestamp must be valid RFC3339 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("timestamp must be UTC")
    return parsed


def _exact_sha(value: str, label: str) -> None:
    if not _SHA_RE.fullmatch(value):
        raise ValueError(f"{label} must be an exact lowercase 40-character SHA")


def _safe_id(value: str, label: str) -> None:
    if not isinstance(value, str) or not _SAFE_ID_RE.fullmatch(value):
        raise ValueError(f"{label} is invalid")


class FactoryState(str, Enum):
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"


class CapabilityState(str, Enum):
    NONE = "NONE"
    BUILDING = "BUILDING"
    VERIFYING = "VERIFYING"
    READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class CellState(str, Enum):
    DISABLED = "DISABLED"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class CellHeartbeat:
    cell_id: str
    observed_at: str
    schedule_minute: int
    state: CellState
    control_plane_sha: str
    run_id: str | None = None
    message: str = ""

    def validate(self) -> None:
        _safe_id(self.cell_id, "cell_id")
        _parse_utc(self.observed_at)
        if not 0 <= self.schedule_minute <= 59:
            raise ValueError("schedule_minute must be between 0 and 59")
        _exact_sha(self.control_plane_sha, "control_plane_sha")
        if self.run_id is not None:
            _safe_id(self.run_id, "run_id")
        if self.state is CellState.RUNNING and self.run_id is None:
            raise ValueError("running heartbeat requires run_id")
        if len(self.message) > 500:
            raise ValueError("heartbeat message is too long")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "cell_id": self.cell_id,
            "observed_at": self.observed_at,
            "schedule_minute": self.schedule_minute,
            "state": self.state.value,
            "control_plane_sha": self.control_plane_sha,
            "run_id": self.run_id,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CellHeartbeat":
        heartbeat = cls(
            cell_id=str(value["cell_id"]),
            observed_at=str(value["observed_at"]),
            schedule_minute=int(value["schedule_minute"]),
            state=CellState(str(value["state"])),
            control_plane_sha=str(value["control_plane_sha"]),
            run_id=None if value.get("run_id") is None else str(value["run_id"]),
            message=str(value.get("message", "")),
        )
        heartbeat.validate()
        return heartbeat


@dataclass(frozen=True)
class ProductReceipt:
    repository: str
    pull_request: int
    capability_fingerprint: str
    base_branch: str
    base_sha: str
    candidate_sha: str
    changed_files: tuple[str, ...]
    product_ci_name: str
    product_ci_run_id: int
    product_ci_sha: str
    product_ci_conclusion: str
    robot_qa_name: str
    robot_qa_run_id: int
    robot_qa_sha: str
    robot_qa_conclusion: str
    state: CapabilityState

    def validate(self) -> None:
        if not _REPOSITORY_RE.fullmatch(self.repository):
            raise ValueError("repository must be owner/name")
        if self.pull_request <= 0:
            raise ValueError("pull_request must be positive")
        _safe_id(self.capability_fingerprint, "capability_fingerprint")
        _safe_id(self.base_branch, "base_branch")
        _exact_sha(self.base_sha, "base_sha")
        _exact_sha(self.candidate_sha, "candidate_sha")
        if self.base_sha == self.candidate_sha:
            raise ValueError("receipt requires a real candidate diff")
        if not self.changed_files or len(set(self.changed_files)) != len(self.changed_files):
            raise ValueError("receipt requires unique changed files")
        if any(not path or path.startswith("/") or ".." in Path(path).parts for path in self.changed_files):
            raise ValueError("receipt contains unsafe changed file path")
        if not self.product_ci_name.strip() or not self.robot_qa_name.strip():
            raise ValueError("CI and Robot QA names are required")
        if self.product_ci_name == self.robot_qa_name:
            raise ValueError("Product CI and Robot QA must be independent checks")
        if self.product_ci_run_id <= 0 or self.robot_qa_run_id <= 0:
            raise ValueError("CI and Robot QA run IDs must be positive")
        _exact_sha(self.product_ci_sha, "product_ci_sha")
        _exact_sha(self.robot_qa_sha, "robot_qa_sha")
        if not self.product_ci_sha == self.robot_qa_sha == self.candidate_sha:
            raise ValueError("candidate, Product CI and Robot QA must use one exact SHA")
        if self.product_ci_conclusion != "success" or self.robot_qa_conclusion != "success":
            raise ValueError("ready receipt requires successful Product CI and Robot QA")
        if self.state is not CapabilityState.READY_FOR_HUMAN_REVIEW:
            raise ValueError("verified product receipt must be READY_FOR_HUMAN_REVIEW")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "repository": self.repository,
            "pull_request": self.pull_request,
            "capability_fingerprint": self.capability_fingerprint,
            "base_branch": self.base_branch,
            "base_sha": self.base_sha,
            "candidate_sha": self.candidate_sha,
            "changed_files": list(self.changed_files),
            "product_ci": {
                "name": self.product_ci_name,
                "run_id": self.product_ci_run_id,
                "sha": self.product_ci_sha,
                "conclusion": self.product_ci_conclusion,
            },
            "robot_qa": {
                "name": self.robot_qa_name,
                "run_id": self.robot_qa_run_id,
                "sha": self.robot_qa_sha,
                "conclusion": self.robot_qa_conclusion,
            },
            "state": self.state.value,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ProductReceipt":
        product_ci = value["product_ci"]
        robot_qa = value["robot_qa"]
        receipt = cls(
            repository=str(value["repository"]),
            pull_request=int(value["pull_request"]),
            capability_fingerprint=str(value["capability_fingerprint"]),
            base_branch=str(value["base_branch"]),
            base_sha=str(value["base_sha"]),
            candidate_sha=str(value["candidate_sha"]),
            changed_files=tuple(str(path) for path in value["changed_files"]),
            product_ci_name=str(product_ci["name"]),
            product_ci_run_id=int(product_ci["run_id"]),
            product_ci_sha=str(product_ci["sha"]),
            product_ci_conclusion=str(product_ci["conclusion"]),
            robot_qa_name=str(robot_qa["name"]),
            robot_qa_run_id=int(robot_qa["run_id"]),
            robot_qa_sha=str(robot_qa["sha"]),
            robot_qa_conclusion=str(robot_qa["conclusion"]),
            state=CapabilityState(str(value["state"])),
        )
        receipt.validate()
        return receipt


@dataclass(frozen=True)
class FactoryStatus:
    schema_version: int
    generation: int
    updated_at: str
    factory_state: FactoryState
    mode: str
    control_plane_sha: str
    enabled_cells: tuple[str, ...]
    max_active_capabilities: int
    max_shreds: int
    active_capability: str | None
    capability_state: CapabilityState
    last_heartbeat: CellHeartbeat
    product_receipt: ProductReceipt | None
    live_log_issue: int

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported factory status schema")
        if self.generation < 0:
            raise ValueError("generation cannot be negative")
        _parse_utc(self.updated_at)
        if self.mode != "PILOT":
            raise ValueError("initial observable activation must remain PILOT")
        _exact_sha(self.control_plane_sha, "control_plane_sha")
        if len(set(self.enabled_cells)) != len(self.enabled_cells):
            raise ValueError("enabled_cells contains duplicates")
        for cell_id in self.enabled_cells:
            _safe_id(cell_id, "enabled cell")
        if len(self.enabled_cells) > 1:
            raise ValueError("pilot observability gate permits one enabled cell")
        if self.max_active_capabilities != 1 or not 1 <= self.max_shreds <= 2:
            raise ValueError("pilot limits must remain one capability and at most two shreds")
        if self.live_log_issue <= 0:
            raise ValueError("live_log_issue must be positive")
        self.last_heartbeat.validate()
        if self.last_heartbeat.control_plane_sha != self.control_plane_sha:
            raise ValueError("heartbeat and status must reference the same control-plane SHA")
        if self.active_capability is None:
            if self.capability_state is not CapabilityState.NONE or self.product_receipt is not None:
                raise ValueError("idle status cannot carry a product receipt")
        else:
            _safe_id(self.active_capability, "active_capability")
            if self.product_receipt is None:
                raise ValueError("active capability requires product receipt")
            self.product_receipt.validate()
            if self.product_receipt.capability_fingerprint != self.active_capability:
                raise ValueError("active capability and receipt fingerprint mismatch")
            if self.capability_state is not self.product_receipt.state:
                raise ValueError("capability state and receipt state mismatch")
        if self.factory_state is FactoryState.RUNNING and not self.enabled_cells:
            raise ValueError("running factory requires one enabled cell")
        if self.factory_state is FactoryState.PAUSED and self.enabled_cells:
            raise ValueError("paused factory cannot list enabled cells")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "generation": self.generation,
            "updated_at": self.updated_at,
            "factory_state": self.factory_state.value,
            "mode": self.mode,
            "control_plane_sha": self.control_plane_sha,
            "enabled_cells": list(self.enabled_cells),
            "limits": {
                "max_active_capabilities": self.max_active_capabilities,
                "max_shreds": self.max_shreds,
            },
            "active_capability": self.active_capability,
            "capability_state": self.capability_state.value,
            "last_heartbeat": self.last_heartbeat.to_dict(),
            "product_receipt": None if self.product_receipt is None else self.product_receipt.to_dict(),
            "live_log_issue": self.live_log_issue,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FactoryStatus":
        limits = value["limits"]
        receipt_value = value.get("product_receipt")
        status = cls(
            schema_version=int(value["schema_version"]),
            generation=int(value["generation"]),
            updated_at=str(value["updated_at"]),
            factory_state=FactoryState(str(value["factory_state"])),
            mode=str(value["mode"]),
            control_plane_sha=str(value["control_plane_sha"]),
            enabled_cells=tuple(str(cell) for cell in value["enabled_cells"]),
            max_active_capabilities=int(limits["max_active_capabilities"]),
            max_shreds=int(limits["max_shreds"]),
            active_capability=None if value.get("active_capability") is None else str(value["active_capability"]),
            capability_state=CapabilityState(str(value["capability_state"])),
            last_heartbeat=CellHeartbeat.from_dict(value["last_heartbeat"]),
            product_receipt=None if receipt_value is None else ProductReceipt.from_dict(receipt_value),
            live_log_issue=int(value["live_log_issue"]),
        )
        status.validate()
        return status

    def render_markdown(self) -> str:
        self.validate()
        receipt = self.product_receipt
        lines = [
            "# RAZZO Factory Live Status",
            "",
            f"- **Factory:** `{self.factory_state.value}`",
            f"- **Mode:** `{self.mode}`",
            f"- **Updated:** `{self.updated_at}`",
            f"- **Control plane SHA:** `{self.control_plane_sha}`",
            f"- **Enabled cells:** `{', '.join(self.enabled_cells) if self.enabled_cells else 'none'}`",
            f"- **Pilot limits:** `{self.max_active_capabilities}` capability / `{self.max_shreds}` shreds",
            f"- **Live operations issue:** `#{self.live_log_issue}`",
            "",
            "## Active capability",
            "",
        ]
        if receipt is None:
            lines.append("No active capability.")
        else:
            lines.extend([
                f"- **Fingerprint:** `{receipt.capability_fingerprint}`",
                f"- **Repository / PR:** `{receipt.repository}#{receipt.pull_request}`",
                f"- **State:** `{receipt.state.value}`",
                f"- **Candidate SHA:** `{receipt.candidate_sha}`",
                f"- **Changed files:** `{len(receipt.changed_files)}`",
                f"- **Product CI:** `{receipt.product_ci_conclusion}` on `{receipt.product_ci_sha}` (run `{receipt.product_ci_run_id}`)",
                f"- **Robot QA:** `{receipt.robot_qa_conclusion}` on `{receipt.robot_qa_sha}` (run `{receipt.robot_qa_run_id}`)",
            ])
        lines.extend([
            "",
            "## Last heartbeat",
            "",
            f"- **Cell:** `{self.last_heartbeat.cell_id}`",
            f"- **State:** `{self.last_heartbeat.state.value}`",
            f"- **Observed:** `{self.last_heartbeat.observed_at}`",
            f"- **Message:** {self.last_heartbeat.message or '—'}",
            "",
            "> Machine-readable source: `razzo/state/factory-status.json`.",
            "> Every scheduled cell must write a start and terminal receipt to the live operations issue.",
            "",
        ])
        return "\n".join(lines)


class StatusConflict(RuntimeError):
    pass


class FactoryStatusStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> FactoryStatus | None:
        if not self.path.exists():
            return None
        return FactoryStatus.from_dict(json.loads(self.path.read_text(encoding="utf-8")))

    def compare_and_swap(self, expected_generation: int, status: FactoryStatus) -> None:
        status.validate()
        current = self.load()
        observed = -1 if current is None else current.generation
        if observed != expected_generation or status.generation != expected_generation + 1:
            raise StatusConflict("factory status generation conflict")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(status.to_dict(), handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
