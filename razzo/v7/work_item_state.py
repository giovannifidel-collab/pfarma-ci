from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TERMINAL_NO_CHANGE = "NO_ACTIONABLE_CHANGE"


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "items": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("items"), dict):
        raise ValueError("work-item state must contain an items object")
    return payload


def _utc(value: datetime | None = None) -> datetime:
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc)


def record_outcome(state: dict[str, Any], item: dict[str, Any], *, outcome: str,
                   run_id: str, candidate_sha: str | None = None,
                   pr_number: int | None = None, now: datetime | None = None) -> dict[str, Any]:
    now = _utc(now)
    fp = str(item["fingerprint"])
    previous = dict(state.setdefault("items", {}).get(fp, {}))
    attempts = int(previous.get("attempts", 0)) + 1
    same_no_change = outcome == TERMINAL_NO_CHANGE and previous.get("last_outcome") in {
        TERMINAL_NO_CHANGE, "REQUIRES_REDISCOVERY"
    }
    no_change_count = int(previous.get("no_actionable_change_count", 0))
    no_change_count = no_change_count + 1 if outcome == TERMINAL_NO_CHANGE else 0
    cooldown_until: str | None = None
    persisted_outcome = outcome
    if outcome == TERMINAL_NO_CHANGE:
        if no_change_count >= 3:
            persisted_outcome = "REQUIRES_REDISCOVERY"
        else:
            hours = 24 if no_change_count >= 2 or same_no_change else 6
            cooldown_until = (now + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")
    record = {
        "work_item_id": item["work_item_id"],
        "project_id": item["project_id"],
        "issue_number": item.get("issue_number"),
        "discovery_source": item.get("discovery_source"),
        "collision_domain": item["collision_domain"],
        "exact_input_sha": item["exact_input_sha"],
        "attempts": attempts,
        "no_actionable_change_count": no_change_count,
        "last_run_id": str(run_id),
        "last_outcome": persisted_outcome,
        "last_attempt_at": now.isoformat().replace("+00:00", "Z"),
        "cooldown_until": cooldown_until,
        "candidate_sha": candidate_sha,
        "pr_number": pr_number,
        "integration_state": "PR_OPEN" if pr_number else previous.get("integration_state", "NONE"),
    }
    record["state_digest"] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    state["items"][fp] = record
    return record


def write(path: Path, state: dict[str, Any]) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
