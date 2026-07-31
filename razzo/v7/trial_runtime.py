from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

from razzo.v7.dispatcher_pool import annotate_work_items
from razzo.v7.product_discovery import select_fairly

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TOPOLOGY = {"discovery": 3, "product": 5, "verify": 1, "integration": 1}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def api_json(token: str, url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def append_output(name: str, value: Any) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        raise RuntimeError("GITHUB_OUTPUT is required")
    rendered = value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))
    with open(output, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={rendered}\n")


def shard_lanes() -> dict[str, list[str]]:
    shards = load_json(ROOT / "razzo/v7/shards.json")["shards"]
    lanes: dict[str, list[str]] = {}
    for lane in EXPECTED_TOPOLOGY:
        lanes[lane] = sorted(
            str(entry["shard_id"])
            for entry in shards
            if entry.get("enabled")
            and entry.get("health") == "healthy"
            and entry.get("supported_lane") == lane
            and not entry.get("current_lease")
        )
    actual = {lane: len(values) for lane, values in lanes.items()}
    if actual != EXPECTED_TOPOLOGY:
        raise RuntimeError(f"invalid ten-shard topology: {actual}")
    return lanes


def command_plan(args: argparse.Namespace) -> int:
    token = os.environ["PFARMA_SOURCE_TOKEN"]
    registry = load_json(ROOT / "razzo/projects.json")
    state = {
        entry["id"]: entry
        for entry in load_json(ROOT / "razzo/project-state.json")["projects"]
    }
    lanes = shard_lanes()
    enabled = [project for project in registry["projects"] if project.get("enabled")]
    if len(enabled) > len(lanes["discovery"]):
        raise RuntimeError("not enough discovery shards for enabled products")

    entries: list[dict[str, Any]] = []
    for index, project in enumerate(enabled):
        project_id = str(project["id"])
        match = re.search(r"issue=#(\d+)", str(state[project_id].get("queueHint", "")))
        if not match:
            raise RuntimeError(f"{project_id} has no explicit queue issue")
        integration_lane = str(project.get("integrationLane", "integration/razzo"))
        encoded_lane = urllib.parse.quote(integration_lane, safe="")
        commit = api_json(
            token,
            f"https://api.github.com/repos/{project['repository']}/commits/{encoded_lane}",
        )
        entries.append(
            {
                "shard_id": lanes["discovery"][index],
                "project_id": project_id,
                "repository": project["repository"],
                "exact_input_sha": commit["sha"],
                "integration_lane": integration_lane,
                "issue_number": int(match.group(1)),
                "task_graph_path": project.get("taskGraphPath", ""),
                "project_json": json.dumps(project, separators=(",", ":")),
            }
        )

    topology = {
        "run_id": args.run_id,
        "mode": args.mode,
        "logical_shard_capacity": 10,
        "topology": {lane: len(values) for lane, values in lanes.items()},
        "discovery": entries,
        "product_progress": False,
    }
    write_json(Path(args.output), topology)
    append_output("discovery_matrix", {"include": entries})
    append_output("discovery_count", str(len(entries)))
    return 0


def command_discovery_prompt(args: argparse.Namespace) -> int:
    issue = load_json(Path(args.issue_file))
    prompt = f"""You are a RAZZO V7 discovery worker. This is a read-only planning task.
Inspect the exact checkout, its tests, product structure, and the explicit portfolio issue below.

PROJECT: {args.project_id}
REPOSITORY: {args.repository}
EXACT SHA: {args.exact_sha}
INTEGRATION LANE: {args.integration_lane}
TASK GRAPH: {args.task_graph_path}
ISSUE #{issue['number']}: {issue['title']}
ISSUE BODY:
{issue.get('body') or ''}

Return JSON only:
{{
  "candidates": [
    {{
      "candidate_id": "stable-short-id",
      "product_objective": "one concrete user-visible behavior",
      "user_impact": "observable benefit",
      "rationale": "evidence from the exact checkout",
      "acceptance_criteria": ["measurable criterion one", "measurable criterion two"],
      "definition_of_done": "measurable completion condition",
      "target_surfaces": ["existing/file/or/directory"],
      "expected_product_effect": "observable product effect",
      "collision_domain": "specific/non-generic-domain",
      "evidence_required": ["focused test", "non-empty diff"],
      "dependencies": []
    }}
  ]
}}

Produce zero to three candidates. Each candidate must be independently deliverable in one
small coherent PR, address a missing or broken product behavior evidenced by the exact checkout,
use only existing tracked files or directories, and have distinct target surfaces and collision
domains. Reject cosmetic-only, documentation-only, receipt, governance, workflow, infrastructure,
migration, secret, real-data, production-write, destructive, paid-infrastructure, human-gated,
vague category, or external-network work. Do not modify files. Return zero candidates when
repository evidence is insufficient.
"""
    Path(args.output).write_text(prompt, encoding="utf-8")
    return 0


def command_aggregate(args: argparse.Namespace) -> int:
    results = [
        load_json(path)
        for path in Path(args.discovery_root).glob("**/result.json")
    ]
    ready = [item for result in results for item in result.get("ready", [])]
    rejected = [item for result in results for item in result.get("rejected", [])]
    project_ids = [str(result["project_id"]) for result in results]
    selected = select_fairly(ready, 5, project_ids)
    workers, leases = annotate_work_items(
        selected,
        provider_cap=5,
        run_id=args.run_id,
    )
    plan = {
        "run_id": args.run_id,
        "mode": args.mode,
        "logical_shard_capacity": 10,
        "ready_candidates": len(ready),
        "selected_product_workers": len(workers),
        "workers": workers,
        "dispatchers": [lease.to_matrix_entry() for lease in leases],
        "rejected": rejected,
        "product_progress": False,
    }
    write_json(Path(args.output), plan)
    append_output("worker_matrix", {"include": workers})
    append_output("worker_count", str(len(workers)))
    print(
        json.dumps(
            {
                "ready_candidates": len(ready),
                "selected_product_workers": len(workers),
                "rejected_candidates": len(rejected),
            },
            indent=2,
        )
    )
    return 0


def command_worker_prompt(args: argparse.Namespace) -> int:
    contract = json.loads(os.environ["CONTRACT_JSON"])
    prompt = f"""You are one RAZZO V7 product worker operating on an exact validated contract.

WORK ITEM: {contract['work_item_id']}
PROJECT: {contract['project_id']}
ISSUE: #{contract['issue_number']} — {contract['issue_title']}
PRODUCT OBJECTIVE: {contract['product_objective']}
USER IMPACT: {contract['user_impact']}
RATIONALE: {contract['rationale']}
ACCEPTANCE CRITERIA: {json.dumps(contract['acceptance_criteria'])}
DEFINITION OF DONE: {contract['definition_of_done']}
TARGET/ALLOWED SURFACES: {json.dumps(contract['allowed_surfaces'])}
FORBIDDEN SURFACES: {json.dumps(contract['forbidden_surfaces'])}
EXPECTED PRODUCT EFFECT: {contract['expected_product_effect']}
EVIDENCE REQUIRED: {json.dumps(contract['evidence_required'])}

Implement only this contract. Modify no file outside allowed surfaces. Do not touch workflows,
infrastructure, migrations, secrets, Factory policy/task graphs, production data, or network
integrations. Do not commit, push, open PRs, or use network commands. Add or update meaningful
focused tests inside allowed surfaces. If the exact checkout does not support the contract,
leave the tree unchanged.
"""
    Path(args.output).write_text(prompt, encoding="utf-8")
    return 0


def command_receipt(args: argparse.Namespace) -> int:
    contract = json.loads(os.environ["CONTRACT_JSON"])
    codex_ok = args.codex_outcome == "success"
    diff_ok = args.diff_outcome in {"success", "skipped"}
    changed = args.has_changes == "true"
    tests_executed = args.tests_executed == "true"
    tests_passed = args.tests_passed == "true"
    if not codex_ok or not diff_ok:
        outcome = "FAILED"
    elif not changed:
        outcome = "NO_ACTIONABLE_CHANGE"
    elif args.tests_outcome != "success":
        outcome = "PRODUCT_CHANGED_TESTS_FAILED"
    elif args.fresh != "true":
        outcome = "STALE_BASE"
    elif not args.pr_number:
        outcome = "PRODUCT_CHANGED_PUBLISH_FAILED"
    else:
        outcome = "PRODUCT_DELIVERED"

    receipt = {
        "run_id": args.run_id,
        "execution_success": codex_ok,
        "product_progress": outcome == "PRODUCT_DELIVERED",
        "outcome": outcome,
        "project_id": contract["project_id"],
        "repository": contract["repository"],
        "issue_number": int(contract["issue_number"]),
        "work_item_id": contract["work_item_id"],
        "fingerprint": contract["fingerprint"],
        "collision_domain": contract["collision_domain"],
        "shard_id": contract["shard_id"],
        "dispatcher_id": contract["dispatcher_id"],
        "lease_digest": contract["lease_digest"],
        "exact_input_sha": contract["exact_input_sha"],
        "integration_lane": contract["integration_lane"],
        "has_changes": changed,
        "tests_executed": tests_executed,
        "tests_passed": tests_passed,
        "candidate_sha": args.candidate_sha or None,
        "pr_number": int(args.pr_number) if args.pr_number else None,
    }
    import hashlib
    receipt["receipt_digest"] = hashlib.sha256(
        json.dumps(receipt, sort_keys=True).encode()
    ).hexdigest()
    write_json(Path(args.output), receipt)
    return 0


def load_receipts(root: str) -> list[dict[str, Any]]:
    base = Path(root)
    if not base.exists():
        return []
    return [load_json(path) for path in base.glob("**/receipt.json")]


def command_verify(args: argparse.Namespace) -> int:
    receipts = load_receipts(args.receipts_root)
    expected = args.expected_count
    if args.mode == "execute-trial" and len(receipts) != expected:
        raise RuntimeError(f"receipt count mismatch: expected {expected}, got {len(receipts)}")
    for key in ("shard_id", "work_item_id", "fingerprint", "collision_domain"):
        values = [receipt[key] for receipt in receipts]
        if len(values) != len(set(values)):
            raise RuntimeError(f"duplicate receipt {key}")

    delivered = sum(receipt["outcome"] == "PRODUCT_DELIVERED" for receipt in receipts)
    changed = sum(bool(receipt["has_changes"]) for receipt in receipts)
    classification = "PLAN_ONLY"
    if args.mode == "execute-trial":
        classification = (
            "PRODUCTIVE"
            if delivered
            else "PARTIALLY_PRODUCTIVE"
            if changed
            else "NON_PRODUCTIVE"
        )
    summary = {
        "run_id": args.run_id,
        "mode": args.mode,
        "logical_shard_capacity": 10,
        "discovery_shards": [
            "razzo-shard-0001",
            "razzo-shard-0007",
            "razzo-shard-0008",
        ],
        "verify_shard": "razzo-shard-0005",
        "planned_product_workers": expected,
        "changed_workers": changed,
        "tested_workers": sum(bool(receipt["tests_executed"]) for receipt in receipts),
        "delivered_prs": delivered,
        "no_actionable_change": sum(
            receipt["outcome"] == "NO_ACTIONABLE_CHANGE" for receipt in receipts
        ),
        "failed_workers": sum(receipt["outcome"] == "FAILED" for receipt in receipts),
        "stale_base": sum(receipt["outcome"] == "STALE_BASE" for receipt in receipts),
        "product_progress": delivered > 0,
        "classification": classification,
    }
    write_json(Path(args.output), summary)
    print(json.dumps(summary, indent=2))
    return 0


def command_integration(args: argparse.Namespace) -> int:
    token = os.environ["PFARMA_SOURCE_TOKEN"]
    receipts = load_receipts(args.receipts_root)
    delivered = [r for r in receipts if r["outcome"] == "PRODUCT_DELIVERED"]
    verified = []
    for receipt in delivered:
        pr = api_json(
            token,
            f"https://api.github.com/repos/{receipt['repository']}/pulls/{receipt['pr_number']}",
        )
        if pr["head"]["sha"] != receipt["candidate_sha"]:
            raise RuntimeError("candidate SHA does not match product PR")
        if pr["base"]["ref"] != receipt["integration_lane"]:
            raise RuntimeError("product PR base does not match integration lane")
        verified.append(
            {
                "repository": receipt["repository"],
                "pr_number": receipt["pr_number"],
                "candidate_sha": receipt["candidate_sha"],
                "base": receipt["integration_lane"],
            }
        )
    readiness = {
        "integration_shard": "razzo-shard-0006",
        "verified_product_prs": verified,
        "auto_merge": False,
        "trial_gate": "manual_review_before_merge",
    }
    write_json(Path(args.output), readiness)
    print(json.dumps(readiness, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan")
    plan.add_argument("--run-id", required=True)
    plan.add_argument("--mode", required=True)
    plan.add_argument("--output", required=True)
    plan.set_defaults(func=command_plan)

    discovery = sub.add_parser("discovery-prompt")
    discovery.add_argument("--issue-file", required=True)
    discovery.add_argument("--project-id", required=True)
    discovery.add_argument("--repository", required=True)
    discovery.add_argument("--exact-sha", required=True)
    discovery.add_argument("--integration-lane", required=True)
    discovery.add_argument("--task-graph-path", required=True)
    discovery.add_argument("--output", required=True)
    discovery.set_defaults(func=command_discovery_prompt)

    aggregate = sub.add_parser("aggregate")
    aggregate.add_argument("--discovery-root", required=True)
    aggregate.add_argument("--run-id", required=True)
    aggregate.add_argument("--mode", required=True)
    aggregate.add_argument("--output", required=True)
    aggregate.set_defaults(func=command_aggregate)

    worker = sub.add_parser("worker-prompt")
    worker.add_argument("--output", required=True)
    worker.set_defaults(func=command_worker_prompt)

    receipt = sub.add_parser("receipt")
    for name in (
        "run_id", "codex_outcome", "diff_outcome", "has_changes", "tests_outcome",
        "tests_executed", "tests_passed", "fresh", "pr_number", "candidate_sha", "output",
    ):
        receipt.add_argument("--" + name.replace("_", "-"), default="")
    receipt.set_defaults(func=command_receipt)

    verify = sub.add_parser("verify")
    verify.add_argument("--receipts-root", required=True)
    verify.add_argument("--expected-count", type=int, required=True)
    verify.add_argument("--mode", required=True)
    verify.add_argument("--run-id", required=True)
    verify.add_argument("--output", required=True)
    verify.set_defaults(func=command_verify)

    integration = sub.add_parser("integration")
    integration.add_argument("--receipts-root", required=True)
    integration.add_argument("--output", required=True)
    integration.set_defaults(func=command_integration)
    return root


def main() -> int:
    args = parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
