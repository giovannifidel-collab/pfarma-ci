#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

TARGETS=("ALDH1","MTORC1","IDH1")
EXPECTED_SHARDS={"ALDH1":27,"MTORC1":27,"IDH1":26}
MICRO_COUNT=4
FORBIDDEN={"label","active","inactive","truth","smiles","experimentalOutcome","originalCompoundId","sourceFile"}


def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path:Path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def main()->None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--source-root",required=True)
    ap.add_argument("--micro-dir",required=True)
    ap.add_argument("--blind-dir",required=True)
    ap.add_argument("--runtime-lock-sha256",required=True)
    ap.add_argument("--gnina-sha256",required=True)
    ap.add_argument("--source-code-sha",required=True)
    ap.add_argument("--output-dir",required=True)
    args=ap.parse_args()

    source_root=Path(args.source_root).resolve()
    policy_path=source_root/"validation"/"v3"/"final_v34_multisignal_transfer_policy.json"
    policy=json.loads(policy_path.read_text())
    if policy.get("status")!="FROZEN_AFTER_V34_DEVELOPMENT_PASS_AND_METADATA_ONLY_TARGET_SELECTION_BEFORE_ANY_V34_EXTERNAL_SCORE":
        raise SystemExit("FAIL-CLOSED policy drift")
    if tuple(policy["externalTargetSelection"]["targets"])!=TARGETS:
        raise SystemExit("FAIL-CLOSED target drift")
    runtime=policy["runtime"]
    if args.runtime_lock_sha256!=runtime["runtimeLockSha256"] or args.gnina_sha256!=runtime["gninaSha256"]:
        raise SystemExit("FAIL-CLOSED runtime drift")
    if args.source_code_sha!="53445632b854cb4970dcf0484f53b248bd9f3813":
        raise SystemExit("FAIL-CLOSED source drift")

    micro_dir=Path(args.micro_dir)
    blind_dir=Path(args.blind_dir)
    out_dir=Path(args.output_dir); out_dir.mkdir(parents=True,exist_ok=True)
    summary={}
    for target in TARGETS:
        blind_candidates=list(blind_dir.rglob(f"{target}.blind.jsonl"))
        if len(blind_candidates)!=1:
            raise SystemExit(f"FAIL-CLOSED blind input count for {target}: {len(blind_candidates)}")
        blind_path=blind_candidates[0]
        blind_rows=read_jsonl(blind_path)
        blind_sha=sha(blind_path)
        n_shards=EXPECTED_SHARDS[target]
        receptor_shas=set()
        policy_shas=set()
        all_rows={}
        for logical in range(n_shards):
            micro_files=sorted(micro_dir.rglob(f"{target}-{logical}-*.jsonl"))
            if len(micro_files)!=MICRO_COUNT:
                raise SystemExit(f"FAIL-CLOSED {target}/{logical} micro file count {len(micro_files)} != {MICRO_COUNT}")
            micro_ids=set(); logical_rows=[]; expected_logical=[r for r in blind_rows if int(r["blindIndex"])%n_shards==logical]
            expected_ids=[str(r["blindId"]) for r in expected_logical]
            for path in micro_files:
                objs=read_jsonl(path)
                if not objs or objs[0].get("recordType")!="executionMetadata":
                    raise SystemExit(f"FAIL-CLOSED execution metadata missing {path}")
                m=objs[0]
                mi=int(m["microIndex"])
                if m.get("status")!="V34_V7_OUTCOME_INDEPENDENT_EXECUTION_MICRO_SHARD" or m.get("target")!=target:
                    raise SystemExit(f"FAIL-CLOSED micro metadata drift {path}")
                if int(m["logicalShardIndex"])!=logical or int(m["logicalShardCount"])!=n_shards or int(m["microCount"])!=MICRO_COUNT or mi in micro_ids or not 0<=mi<MICRO_COUNT:
                    raise SystemExit(f"FAIL-CLOSED micro identity drift {path}")
                if m.get("truthAvailableToWorker") is not False or m.get("labelsRead") is not False:
                    raise SystemExit("FAIL-CLOSED truth isolation drift")
                if str(m.get("blindInputSha256"))!=blind_sha or str(m.get("runtimeLockSha256"))!=args.runtime_lock_sha256 or str(m.get("gninaBinarySha256"))!=args.gnina_sha256 or str(m.get("sourceCodeSha"))!=args.source_code_sha:
                    raise SystemExit("FAIL-CLOSED execution provenance drift")
                if int(m["logicalSelectedRecords"])!=len(expected_logical) or len(objs)-1!=int(m["microSelectedRecords"]):
                    raise SystemExit("FAIL-CLOSED execution cardinality drift")
                micro_ids.add(mi); receptor_shas.add(str(m["receptorManifestSha256"])); policy_shas.add(str(m["transferPolicySha256"]))
                expected_micro=expected_logical[mi::MICRO_COUNT]
                got=objs[1:]
                if [int(x["blindIndex"]) for x in got] != [int(x["blindIndex"]) for x in expected_micro]:
                    raise SystemExit(f"FAIL-CLOSED micro deterministic selection drift {target}/{logical}/{mi}")
                if [str(x["blindId"]) for x in got] != [str(x["blindId"]) for x in expected_micro]:
                    raise SystemExit(f"FAIL-CLOSED micro identity drift {target}/{logical}/{mi}")
                for row in got:
                    if FORBIDDEN.intersection(row):
                        raise SystemExit("FAIL-CLOSED forbidden truth-bearing field in execution output")
                    if not set(row).issubset({"blindIndex","blindId","status","seed","receptors","ligandPreparation","failureCode"}):
                        raise SystemExit("FAIL-CLOSED unknown score fields")
                    idx=int(row["blindIndex"])
                    if idx%n_shards!=logical or idx in all_rows:
                        raise SystemExit("FAIL-CLOSED duplicate/wrong logical shard row")
                    all_rows[idx]=row; logical_rows.append(row)
            if micro_ids!=set(range(MICRO_COUNT)):
                raise SystemExit("FAIL-CLOSED incomplete micro coverage")
            logical_rows=sorted(logical_rows,key=lambda x:int(x["blindIndex"]))
            if [str(x["blindId"]) for x in logical_rows]!=expected_ids:
                raise SystemExit(f"FAIL-CLOSED recombined identity/order mismatch {target}/{logical}")
            if len(receptor_shas)!=1 or len(policy_shas)!=1:
                raise SystemExit("FAIL-CLOSED inconsistent provenance")
            meta={
                "recordType":"metadata",
                "suite":policy["suite"],
                "version":"3.4.0-external-blind1",
                "target":target,
                "scientificRole":"BLIND_HOLDOUT_SCORING_NO_LABELS",
                "ranker":"rank_consensus_all3",
                "requiredSignals":["cnnaffinity_max","vina_best","cnnscore_mean3"],
                "shardIndex":logical,
                "shardCount":n_shards,
                "selectedRecords":len(logical_rows),
                "totalBlindRecords":len(blind_rows),
                "blindInputSha256":blind_sha,
                "receptorManifestSha256":next(iter(receptor_shas)),
                "transferPolicySha256":sha(policy_path),
                "runtimeLockSha256":args.runtime_lock_sha256,
                "gninaBinarySha256":args.gnina_sha256,
                "sourceCodeSha":args.source_code_sha,
                "truthAvailableToWorker":False,
                "labelsRead":False,
                "numModes":policy["docking"]["numModes"],
                "receptorWeights":[0.5,0.5],
            }
            out=out_dir/f"{target}-{logical}.jsonl"
            with out.open("w",encoding="utf-8") as f:
                f.write(json.dumps(meta,sort_keys=True)+"\n")
                for row in logical_rows:
                    f.write(json.dumps(row,sort_keys=True)+"\n")
        if set(all_rows)!=set(range(len(blind_rows))):
            raise SystemExit(f"FAIL-CLOSED exact target coverage failure {target}")
        summary[target]={"records":len(all_rows),"logicalShards":n_shards,"microShards":n_shards*MICRO_COUNT,"failedLigands":sum(r.get("status")!="OK" for r in all_rows.values())}
    if sum(v["records"] for v in summary.values())!=2458 or sum(v["logicalShards"] for v in summary.values())!=80:
        raise SystemExit("FAIL-CLOSED aggregate recombination drift")
    print(json.dumps({"status":"V34_V7_EXECUTION_MICRO_SHARDS_RECOMBINED_TO_FROZEN_80_LOGICAL_SHARDS","truthRead":False,"truthAvailable":False,"targets":summary},indent=2,sort_keys=True))


if __name__=="__main__":
    main()
