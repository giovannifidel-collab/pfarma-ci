import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROOF = ROOT / "razzo" / "state" / "factory-finalization.json"
SHA = re.compile(r"^[0-9a-f]{40}$")


def load_proof() -> dict:
    return json.loads(PROOF.read_text(encoding="utf-8"))


def test_factory_is_finalized_product_first() -> None:
    proof = load_proof()
    assert proof["schema"] == "razzo.factory-finalization.v1"
    assert proof["status"] == "FINALIZED_PRODUCT_FIRST"
    assert proof["control_plane"]["mode"] == "FROZEN_PRODUCT_FIRST"
    assert proof["control_plane"]["future_change_policy"] == "PRODUCT_BLOCKING_BUG_ONLY"


def test_three_unique_product_deliveries_are_integrated() -> None:
    proof = load_proof()
    deliveries = proof["deliveries"]
    repositories = {delivery["repository"] for delivery in deliveries}
    assert repositories == {
        "giovannifidel-collab/project-giovanni",
        "giovannifidel-collab/pfarma-cloud",
        "giovannifidel-collab/family-cloud",
    }
    assert len(deliveries) == len(repositories) == 3
    for delivery in deliveries:
        assert delivery["pr"] > 0
        assert SHA.fullmatch(delivery["candidate_sha"])
        assert SHA.fullmatch(delivery["merge_sha"])
        assert delivery["product_ci_run"] > 0
        assert delivery["robot_qa_run"] > 0
        assert delivery["user_journey"].strip()
        assert delivery["sensitive_writes"] == 0


def test_finalization_thresholds_and_safety_hold() -> None:
    result = load_proof()["proof"]
    assert result["product_repositories"] == 3
    assert result["integrations"] >= 2
    assert result["autonomous_red_repairs"] >= 1
    assert result["robot_journeys_green"] == 3
    assert result["duplicate_deliveries"] == 0
    assert result["collision_violations"] == 0
    assert result["sensitive_writes"] == 0
    assert result["product_main_writes"] == 0


def test_at_least_one_red_pr_was_repaired_in_place() -> None:
    deliveries = load_proof()["deliveries"]
    assert sum(bool(delivery["corrected_from_red"]) for delivery in deliveries) >= 1
