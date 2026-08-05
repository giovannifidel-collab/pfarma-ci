from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAUNCH = ROOT / "razzo/state/autonomous-launch.json"
PROJECTS = ROOT / "razzo/projects.json"
PROJECT_STATE = ROOT / "razzo/project-state.json"
PUBLIC_FABRIC = ROOT / "razzo/public_fabric/config.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def validate() -> dict:
    launch = load(LAUNCH)
    projects = load(PROJECTS)
    state = load(PROJECT_STATE)
    fabric = load(PUBLIC_FABRIC)

    require(launch.get("status") == "RUNNING", "factory status must be RUNNING")
    require(launch.get("mode") == "AUTONOMOUS_MULTI_PROJECT", "factory mode mismatch")
    require(launch.get("sourceOfTruth") == "github", "GitHub must remain source of truth")

    controller = launch.get("cognitiveController", {})
    require(controller.get("type") == "chatgpt-scheduled-automations", "cognitive controller missing")
    triggers = controller.get("triggers", [])
    require(len(triggers) == 5, "exactly five controller triggers are required")
    require(sorted(item.get("minute") for item in triggers) == [0, 12, 24, 36, 48], "trigger minutes mismatch")
    require(all(item.get("enabled") is True for item in triggers), "all controller triggers must be enabled")
    require(len({item.get("id") for item in triggers}) == 5, "controller trigger IDs must be unique")
    digest = controller.get("promptDigestSha256", "")
    require(len(digest) == 64 and all(ch in "0123456789abcdef" for ch in digest), "invalid canonical prompt digest")

    enabled = [project for project in projects.get("projects", []) if project.get("enabled", True)]
    declared = launch.get("portfolio", {}).get("enabledProjects", [])
    require(sorted(project["id"] for project in enabled) == sorted(declared), "launch portfolio differs from registry")
    require(state.get("factoryAllocationPaused") is False, "factory allocation is paused")
    state_by_id = {project["id"]: project for project in state.get("projects", [])}
    require(set(state_by_id) == set(declared), "project state differs from enabled portfolio")
    require(all(not project.get("humanGate") for project in state_by_id.values()), "an active portfolio-wide human gate exists")

    execution = launch.get("executionFabric", {})
    require(execution.get("type") == "github-public-execution-fabric", "public execution fabric missing")
    configured_shards = fabric.get("shards", [])
    require(execution.get("configuredActiveShards") == len(configured_shards), "configured shard count mismatch")
    proof = execution.get("lastVerifiedWave", {})
    require(proof.get("dispatched", 0) > 0, "no real wave was dispatched")
    require(proof.get("dispatched") == proof.get("completed") == proof.get("verified"), "wave completion/verification mismatch")
    require(proof.get("failures") == 0, "last verified wave contains failures")
    require(proof.get("productProgress") is False, "deterministic fabric proof must not be mislabeled as product progress")

    policy = launch.get("integrationPolicy", {})
    for key in (
        "registeredIntegrationLanesOnly",
        "exactCandidateShaRequired",
        "productCiRequired",
        "independentRobotQaRequired",
        "expectedHeadRequired",
        "automaticLaneMergeWhenSafe",
    ):
        require(policy.get(key) is True, f"integration policy {key} is not enabled")
    require(policy.get("productMainWrites") is False, "product main writes must remain disabled")

    gate = launch.get("launchGate", {})
    require(gate and all(value is True for value in gate.values()), "launch gate is incomplete")

    return {
        "status": "RAZZO_AUTONOMOUS_FACTORY_LAUNCH_GATE_GREEN",
        "controllers": len(triggers),
        "projects": len(enabled),
        "shards": len(configured_shards),
        "lastVerifiedWave": proof.get("cycleId"),
        "workflowRunId": proof.get("workflowRunId"),
    }


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True))
