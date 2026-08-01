from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any

from razzo.v7.dispatcher_pool import annotate_work_items
from razzo.v7.product_discovery import select_fairly
from razzo.v7.trial_runtime import api_json, append_output, load_json, write_json

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TOPOLOGY = {"discovery": 3, "product": 8, "verify": 1, "integration": 1}
LOGICAL_SHARD_CAPACITY = sum(EXPECTED_TOPOLOGY.values())
PRODUCT_CAP = EXPECTED_TOPOLOGY["product"]


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
        raise RuntimeError(f"invalid scaled shard topology: {actual}")
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
        "logical_shard_capacity": LOGICAL_SHARD_CAPACITY,
        "topology": {lane: len(values) for lane, values in lanes.items()},
        "discovery": entries,
        "product_progress": False,
    }
    write_json(Path(args.output), topology)
    append_output("discovery_matrix", {"include": entries})
    append_output("discovery_count", str(len(entries)))
    return 0


def command_aggregate(args: argparse.Namespace) -> int:
    results = [
        load_json(path)
        for path in Path(args.discovery_root).glob("**/result.json")
    ]
    ready = [item for result in results for item in result.get("ready", [])]
    rejected = [item for result in results for item in result.get("rejected", [])]
    project_ids = [str(result["project_id"]) for result in results]
    selected = select_fairly(ready, PRODUCT_CAP, project_ids)
    workers, leases = annotate_work_items(
        selected,
        provider_cap=PRODUCT_CAP,
        run_id=args.run_id,
    )
    plan = {
        "run_id": args.run_id,
        "mode": args.mode,
        "logical_shard_capacity": LOGICAL_SHARD_CAPACITY,
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
    print(json.dumps({
        "ready_candidates": len(ready),
        "selected_product_workers": len(workers),
        "rejected_candidates": len(rejected),
        "product_cap": PRODUCT_CAP,
    }, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan")
    plan.add_argument("--run-id", required=True)
    plan.add_argument("--mode", required=True)
    plan.add_argument("--output", required=True)
    plan.set_defaults(func=command_plan)

    aggregate = sub.add_parser("aggregate")
    aggregate.add_argument("--discovery-root", required=True)
    aggregate.add_argument("--run-id", required=True)
    aggregate.add_argument("--mode", required=True)
    aggregate.add_argument("--output", required=True)
    aggregate.set_defaults(func=command_aggregate)
    return root


def main() -> int:
    args = parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
