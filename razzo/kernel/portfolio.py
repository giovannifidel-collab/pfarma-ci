from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PortfolioProject:
    project_id: str
    repository: str
    integration_lane: str
    enabled: bool
    protect_main: bool
    normal_concurrency: int


@dataclass(frozen=True)
class PortfolioSnapshot:
    source_path: str
    source_digest: str
    projects: tuple[PortfolioProject, ...]

    @property
    def enabled_projects(self) -> tuple[PortfolioProject, ...]:
        return tuple(project for project in self.projects if project.enabled)

    def require_enabled(self) -> tuple[PortfolioProject, ...]:
        enabled = self.enabled_projects
        if not enabled:
            raise ValueError("portfolio contains no enabled projects")
        return enabled


def _project_from_raw(raw: dict[str, Any]) -> PortfolioProject:
    project_id = str(raw.get("id", "")).strip()
    repository = str(raw.get("repository", "")).strip()
    if not project_id or not repository:
        raise ValueError("every project requires id and repository")
    concurrency = int(raw.get("normalConcurrency", 1))
    if concurrency < 1:
        raise ValueError(f"normalConcurrency must be positive for {project_id}")
    return PortfolioProject(
        project_id=project_id,
        repository=repository,
        integration_lane=str(raw.get("integrationLane") or "integration/razzo"),
        enabled=bool(raw.get("enabled", True)),
        protect_main=bool(raw.get("protectMain", True)),
        normal_concurrency=concurrency,
    )


def load_portfolio(path: str | Path) -> PortfolioSnapshot:
    source = Path(path)
    raw_bytes = source.read_bytes()
    payload = json.loads(raw_bytes.decode("utf-8"))
    raw_projects = payload.get("projects")
    if not isinstance(raw_projects, list):
        raise ValueError("projects must be a list")

    projects = tuple(_project_from_raw(item) for item in raw_projects)
    ids = [project.project_id for project in projects]
    repositories = [project.repository for project in projects]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate project id")
    if len(repositories) != len(set(repositories)):
        raise ValueError("duplicate project repository")

    return PortfolioSnapshot(
        source_path=str(source),
        source_digest=hashlib.sha256(raw_bytes).hexdigest(),
        projects=projects,
    )
