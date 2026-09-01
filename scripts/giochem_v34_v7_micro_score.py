#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, importlib.metadata, json, os, sys, tempfile, shutil
from pathlib import Path

FROZEN_SOURCE_SHA = "53445632b854cb4970dcf0484f53b248bd9f3813"
TARGETS = ("ALDH1", "MTORC1", "IDH1")
EXPECTED_SHARDS = {"ALDH1": 27, "MTORC1": 27, "IDH1": 26}
MICRO_COUNT = 4


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-root", required=True)
    ap.add_argument("--target", required=True, choices=TARGETS)
    ap.add_argument("--blind-input", required=True)
    ap.add_argument("--receptor-dir", required=True)
    ap.add_argument("--receptor-manifest", required=True)
    ap.add_argument("--runtime-lock-sha256", required=True)
    ap.add_argument("--source-code-sha", required=True)
    ap.add_argument("--logical-shard-index", type=int, required=True)
    ap.add_argument("--logical-shard-count", type=int, required=True)
    ap.add_argument("--micro-index", type=int, required=True)
    ap.add_argument("--micro-count", type=int, default=MICRO_COUNT)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    source_root = Path(args.source_root).resolve()
    if args.source_code_sha != FROZEN_SOURCE_SHA:
        raise SystemExit("FAIL-CLOSED frozen source SHA drift")
    scripts = source_root / "scripts"
    sys.path.insert(0, str(scripts))
    import validation_v34_blind_score_worker as worker
    import validation_v34_multisignal_dev_worker as dev
    import validation_v31_gnina_ampc_worker_static as static_helpers

    expected = EXPECTED_SHARDS[args.target]
    if args.logical_shard_count != expected or not 0 <= args.logical_shard_index < expected:
        raise SystemExit("FAIL-CLOSED logical shard layout drift")
    if args.micro_count != MICRO_COUNT or not 0 <= args.micro_index < MICRO_COUNT:
        raise SystemExit("FAIL-CLOSED execution micro-shard layout drift")

    policy_path = source_root / "validation" / "v3" / "final_v34_multisignal_transfer_policy.json"
    policy = json.loads(policy_path.read_text())
    if policy.get("status") != "FROZEN_AFTER_V34_DEVELOPMENT_PASS_AND_METADATA_ONLY_TARGET_SELECTION_BEFORE_ANY_V34_EXTERNAL_SCORE":
        raise SystemExit("FAIL-CLOSED V34 transfer policy drift")
    if tuple(policy["externalTargetSelection"]["targets"]) != TARGETS:
        raise SystemExit("FAIL-CLOSED target drift")
    runtime = policy["runtime"]
    if importlib.metadata.version("meeko") != str(runtime["meeko"]) or importlib.metadata.version("rdkit") != str(runtime["rdkit"]):
        raise SystemExit("FAIL-CLOSED ligand runtime drift")
    exe = Path(os.environ.get("GIOCHEM_GNINA_BIN", ""))
    if not exe.is_file() or static_helpers.sha256_file(exe) != runtime["gninaSha256"]:
        raise SystemExit("FAIL-CLOSED frozen GNINA drift")
    if args.runtime_lock_sha256 != runtime["runtimeLockSha256"]:
        raise SystemExit("FAIL-CLOSED frozen runtime lock drift")

    blind_path = Path(args.blind_input)
    rows = dev.load_blind(blind_path)
    receptors, receptor_sha = dev.load_receptors(args.target, Path(args.receptor_dir), Path(args.receptor_manifest))
    logical = [r for r in rows if int(r["blindIndex"]) % args.logical_shard_count == args.logical_shard_index]
    micro = logical[args.micro_index::args.micro_count]
    if len(micro) > 10:
        raise SystemExit(f"FAIL-CLOSED micro-shard too large: {len(micro)}")
    if logical and len(micro) > (len(logical) + 2) // 3:
        raise SystemExit("FAIL-CLOSED micro-shard exceeds one-third execution bound")

    protocol = {
        "suite": policy["suite"],
        "version": policy["version"],
        "docking": policy["docking"],
        "signals": ["cnnaffinity_max", "vina_best", "cnnscore_mean3"],
    }
    meta = {
        "recordType": "executionMetadata",
        "status": "V34_V7_OUTCOME_INDEPENDENT_EXECUTION_MICRO_SHARD",
        "target": args.target,
        "logicalShardIndex": args.logical_shard_index,
        "logicalShardCount": args.logical_shard_count,
        "microIndex": args.micro_index,
        "microCount": args.micro_count,
        "logicalSelectedRecords": len(logical),
        "microSelectedRecords": len(micro),
        "totalBlindRecords": len(rows),
        "blindInputSha256": file_sha256(blind_path),
        "receptorManifestSha256": receptor_sha,
        "transferPolicySha256": file_sha256(policy_path),
        "runtimeLockSha256": args.runtime_lock_sha256,
        "gninaBinarySha256": runtime["gninaSha256"],
        "sourceCodeSha": args.source_code_sha,
        "truthAvailableToWorker": False,
        "labelsRead": False,
        "selectionRule": "logical=(blindIndex % logicalShardCount); micro=logical_order[microIndex::4]",
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"giochem-v34-v7-{args.target}-{args.logical_shard_index}-{args.micro_index}-") as td, out_path.open("w", encoding="utf-8") as out:
        out.write(json.dumps(meta, sort_keys=True) + "\n")
        root = Path(td)
        for n, row in enumerate(micro, 1):
            out.write(json.dumps(worker.score_one(args.target, row, receptors, exe, root, protocol), sort_keys=True) + "\n")
            out.flush()
            print(f"V3.4 V7 {args.target} logical {args.logical_shard_index} micro {args.micro_index}: {n}/{len(micro)}", flush=True)

    objs = [json.loads(x) for x in out_path.read_text().splitlines()[1:] if x.strip()]
    if len(objs) != len(micro):
        raise SystemExit("FAIL-CLOSED micro output cardinality drift")
    forbidden = {"label", "active", "inactive", "truth", "smiles", "experimentalOutcome", "originalCompoundId", "sourceFile"}
    if any(forbidden.intersection(obj) for obj in objs):
        raise SystemExit("FAIL-CLOSED forbidden truth-bearing field in micro output")
    print(json.dumps({"target": args.target, "logicalShard": args.logical_shard_index, "micro": args.micro_index, "records": len(objs), "failures": sum(x.get("status") != "OK" for x in objs)}))


if __name__ == "__main__":
    main()
