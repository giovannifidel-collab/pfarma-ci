from __future__ import annotations

"""Controlled six-worker compatibility runtime.

The existing workflow already invokes this module. We preserve the proven trial runtime,
expand only the product lane from five to six, and leave all receipt, verification and
integration behavior unchanged.
"""

from typing import Any

from razzo.v7 import trial_runtime

_ORIGINAL_SELECT = trial_runtime.select_fairly
_ORIGINAL_ANNOTATE = trial_runtime.annotate_work_items

trial_runtime.EXPECTED_TOPOLOGY = {
    "discovery": 3,
    "product": 6,
    "verify": 1,
    "integration": 1,
}


def _select_six(ready: list[dict[str, Any]], _limit: int, project_ids: list[str]) -> list[dict[str, Any]]:
    return _ORIGINAL_SELECT(ready, 6, project_ids)


def _annotate_six(work_items: list[dict[str, Any]], *, provider_cap: int, run_id: str):
    return _ORIGINAL_ANNOTATE(work_items, provider_cap=6, run_id=run_id)


trial_runtime.select_fairly = _select_six
trial_runtime.annotate_work_items = _annotate_six


if __name__ == "__main__":
    raise SystemExit(trial_runtime.main())
