from __future__ import annotations

import argparse
import json
from pathlib import Path

ARTIFACTS = {
    "contract": {"allowed_warehouses": ["A", "E"], "quantity_type": "non_negative_integer", "result_fields": ["source", "destination", "quantity", "source_after", "destination_after", "production_write"]},
    "logic": {"formula": {"source_after": "source_available - quantity", "destination_after": "destination_available + quantity"}},
    "safety": {"rules": ["source and destination must be different", "warehouses must be A or E", "quantity must not exceed source_available", "production_write is always false"]},
    "happy_tests": {"cases": [{"source": "E", "destination": "A", "quantity": 3, "source_available": 10, "destination_available": 4, "expected": [7, 7]}]},
    "error_tests": {"cases": ["same warehouse rejected", "unsupported warehouse rejected", "insufficient stock rejected", "negative quantity rejected"]},
    "integrate": {"requires": ["contract", "logic", "safety", "happy_tests", "error_tests"]},
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shred-json", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    shred = json.loads(args.shred_json)
    artifact_name = shred["artifact"]
    if artifact_name not in ARTIFACTS:
        raise SystemExit(f"unknown artifact {artifact_name}")
    payload = {
        "schema": "razzo-shred-artifact-v1",
        "shred_id": shred["shred_id"],
        "artifact": artifact_name,
        "idempotency_key": shred["idempotency_key"],
        "payload": ARTIFACTS[artifact_name],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"shred_id": shred["shred_id"], "artifact": artifact_name}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
