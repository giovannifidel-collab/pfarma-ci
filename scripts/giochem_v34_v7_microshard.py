#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

FORBIDDEN = {'label','active','inactive','truth','smiles','experimentalOutcome','originalCompoundId','sourceFile'}
TARGETS = ('ALDH1','MTORC1','IDH1')
EXPECTED_SHARDS = {'ALDH1':27,'MTORC1':27,'IDH1':26}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def load_frozen(source_root: Path):
    scripts = source_root / 'scripts'
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import validation_v34_blind_score_worker as worker
    return worker


def validate_frozen(worker, target: str, runtime_lock: str, source_sha: str, receptor_dir: Path, receptor_manifest: Path):
    policy = json.loads(worker.POLICY.read_text())
    if policy.get('status') != 'FROZEN_AFTER_V34_DEVELOPMENT_PASS_AND_METADATA_ONLY_TARGET_SELECTION_BEFORE_ANY_V34_EXTERNAL_SCORE':
        raise SystemExit('FAIL-CLOSED V34 transfer policy drift')
    if tuple(policy['externalTargetSelection']['targets']) != TARGETS:
        raise SystemExit('FAIL-CLOSED external target drift')
    runtime = policy['runtime']
    if importlib.metadata.version('meeko') != str(runtime['meeko']) or importlib.metadata.version('rdkit') != str(runtime['rdkit']):
        raise SystemExit('FAIL-CLOSED ligand runtime drift')
    exe = Path(os.environ.get('GIOCHEM_GNINA_BIN',''))
    if not exe.is_file() or worker.static_helpers.sha256_file(exe) != runtime['gninaSha256'] or runtime_lock != runtime['runtimeLockSha256']:
        raise SystemExit('FAIL-CLOSED frozen runtime drift')
    receptors, receptor_sha = worker.dev.load_receptors(target, receptor_dir, receptor_manifest)
    protocol = {'suite':policy['suite'],'version':policy['version'],'docking':policy['docking'],'signals':['cnnaffinity_max','vina_best','cnnscore_mean3']}
    return policy, runtime, exe, receptors, receptor_sha, protocol


def score_micro(args) -> None:
    source_root = Path(args.source_root).resolve()
    worker = load_frozen(source_root)
    if args.target not in TARGETS:
        raise SystemExit('FAIL-CLOSED target')
    expected = EXPECTED_SHARDS[args.target]
    if args.logical_count != expected or not 0 <= args.logical_shard < expected:
        raise SystemExit('FAIL-CLOSED logical shard layout drift')
    if args.micro_count != 3 or not 0 <= args.micro_index < args.micro_count:
        raise SystemExit('FAIL-CLOSED V7 execution microshard layout drift')
    blind = Path(args.blind_input)
    rmanifest = Path(args.receptor_manifest)
    policy, runtime, exe, receptors, receptor_sha, protocol = validate_frozen(
        worker, args.target, args.runtime_lock_sha256, args.source_code_sha, Path(args.receptor_dir), rmanifest
    )
    rows = worker.dev.load_blind(blind)
    logical = [r for r in rows if int(r['blindIndex']) % args.logical_count == args.logical_shard]
    selected = [r for pos, r in enumerate(logical) if pos % args.micro_count == args.micro_index]
    if not selected:
        raise SystemExit('FAIL-CLOSED empty execution microshard')
    meta = {
        'recordType':'metadata',
        'suite':policy['suite'],
        'version':'3.4.0-external-blind1',
        'target':args.target,
        'scientificRole':'BLIND_HOLDOUT_SCORING_NO_LABELS',
        'ranker':'rank_consensus_all3',
        'requiredSignals':['cnnaffinity_max','vina_best','cnnscore_mean3'],
        'shardIndex':args.logical_shard,
        'shardCount':args.logical_count,
        'selectedRecords':len(selected),
        'logicalSelectedRecords':len(logical),
        'totalBlindRecords':len(rows),
        'blindInputSha256':worker.dev.sha256_file(blind),
        'receptorManifestSha256':receptor_sha,
        'transferPolicySha256':worker.dev.sha256_file(worker.POLICY),
        'runtimeLockSha256':args.runtime_lock_sha256,
        'gninaBinarySha256':runtime['gninaSha256'],
        'sourceCodeSha':args.source_code_sha,
        'truthAvailableToWorker':False,
        'labelsRead':False,
        'numModes':policy['docking']['numModes'],
        'receptorWeights':[0.5,0.5],
        'executionMode':'V7_DETERMINISTIC_MICROSHARD_RECOVERY',
        'executionMicroIndex':args.micro_index,
        'executionMicroCount':args.micro_count,
    }
    out = Path(args.output)
    with tempfile.TemporaryDirectory(prefix=f'giochem-v34-v7-{args.target}-{args.logical_shard}-{args.micro_index}-') as td, out.open('w', encoding='utf-8') as fh:
        fh.write(json.dumps(meta, sort_keys=True) + '\n')
        root = Path(td)
        for n, row in enumerate(selected, 1):
            result = worker.score_one(args.target, row, receptors, exe, root, protocol)
            if FORBIDDEN.intersection(result):
                raise SystemExit('FAIL-CLOSED forbidden score field')
            fh.write(json.dumps(result, sort_keys=True) + '\n')
            fh.flush()
            if n % 5 == 0:
                print(f'V7 {args.target} logical {args.logical_shard} micro {args.micro_index}: {n}/{len(selected)}', flush=True)
    objs = read_jsonl(out)[1:]
    if len(objs) != len(selected):
        raise SystemExit('FAIL-CLOSED micro output cardinality drift')
    failures = sum(r.get('status') != 'OK' for r in objs)
    if failures / len(objs) > 0.25:
        raise SystemExit(4)
    print(json.dumps({'target':args.target,'logicalShard':args.logical_shard,'microIndex':args.micro_index,'records':len(objs),'failures':failures}, sort_keys=True))


def recombine_one(args) -> None:
    source_root = Path(args.source_root).resolve()
    worker = load_frozen(source_root)
    expected = EXPECTED_SHARDS[args.target]
    if args.logical_count != expected or not 0 <= args.logical_shard < expected or args.micro_count != 3:
        raise SystemExit('FAIL-CLOSED recombine layout drift')
    blind = Path(args.blind_input)
    rows = worker.dev.load_blind(blind)
    logical = [r for r in rows if int(r['blindIndex']) % args.logical_count == args.logical_shard]
    expected_ids = {int(r['blindIndex']): str(r['blindId']) for r in logical}
    files = sorted(Path(args.micro_dir).rglob(f'{args.target}-{args.logical_shard}-micro-*.jsonl'))
    if len(files) != args.micro_count:
        raise SystemExit(f'FAIL-CLOSED micro file count {len(files)} != {args.micro_count}')
    metas = []
    by_index: dict[int, dict[str, Any]] = {}
    seen_micro = set()
    for path in files:
        objs = read_jsonl(path)
        if not objs or objs[0].get('recordType') != 'metadata':
            raise SystemExit('FAIL-CLOSED micro metadata missing')
        meta = objs[0]
        mi = int(meta.get('executionMicroIndex', -1))
        if meta.get('executionMode') != 'V7_DETERMINISTIC_MICROSHARD_RECOVERY' or int(meta.get('executionMicroCount', -1)) != args.micro_count or mi in seen_micro:
            raise SystemExit('FAIL-CLOSED micro execution provenance drift')
        seen_micro.add(mi)
        if meta.get('target') != args.target or int(meta.get('shardIndex', -1)) != args.logical_shard or int(meta.get('shardCount', -1)) != args.logical_count:
            raise SystemExit('FAIL-CLOSED logical shard identity drift')
        if meta.get('truthAvailableToWorker') is not False or meta.get('labelsRead') is not False:
            raise SystemExit('FAIL-CLOSED truth isolation drift')
        if len(objs) - 1 != int(meta.get('selectedRecords', -1)):
            raise SystemExit('FAIL-CLOSED micro selected count drift')
        metas.append(meta)
        for row in objs[1:]:
            if FORBIDDEN.intersection(row):
                raise SystemExit('FAIL-CLOSED forbidden score field')
            idx = int(row['blindIndex'])
            if idx in by_index or idx not in expected_ids or str(row['blindId']) != expected_ids[idx]:
                raise SystemExit('FAIL-CLOSED duplicate/wrong micro score identity')
            by_index[idx] = row
    if seen_micro != set(range(args.micro_count)) or set(by_index) != set(expected_ids):
        raise SystemExit('FAIL-CLOSED exact logical shard coverage failure')
    stable_keys = ['suite','version','target','scientificRole','ranker','requiredSignals','shardIndex','shardCount','totalBlindRecords','blindInputSha256','receptorManifestSha256','transferPolicySha256','runtimeLockSha256','gninaBinarySha256','sourceCodeSha','truthAvailableToWorker','labelsRead','numModes','receptorWeights']
    base = metas[0]
    for meta in metas[1:]:
        for key in stable_keys:
            if meta.get(key) != base.get(key):
                raise SystemExit(f'FAIL-CLOSED inconsistent micro provenance {key}')
    final_meta = {key: base[key] for key in stable_keys}
    final_meta['recordType'] = 'metadata'
    final_meta['selectedRecords'] = len(logical)
    out = Path(args.output)
    with out.open('w', encoding='utf-8') as fh:
        fh.write(json.dumps(final_meta, sort_keys=True) + '\n')
        for idx in sorted(by_index):
            fh.write(json.dumps(by_index[idx], sort_keys=True) + '\n')
    print(json.dumps({'target':args.target,'logicalShard':args.logical_shard,'records':len(logical),'status':'RECOMBINED'}, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('score')
    s.add_argument('--source-root', required=True); s.add_argument('--target', required=True); s.add_argument('--blind-input', required=True)
    s.add_argument('--receptor-dir', required=True); s.add_argument('--receptor-manifest', required=True); s.add_argument('--runtime-lock-sha256', required=True)
    s.add_argument('--source-code-sha', required=True); s.add_argument('--logical-shard', type=int, required=True); s.add_argument('--logical-count', type=int, required=True)
    s.add_argument('--micro-index', type=int, required=True); s.add_argument('--micro-count', type=int, required=True); s.add_argument('--output', required=True)
    r = sub.add_parser('recombine')
    r.add_argument('--source-root', required=True); r.add_argument('--target', required=True); r.add_argument('--blind-input', required=True); r.add_argument('--micro-dir', required=True)
    r.add_argument('--logical-shard', type=int, required=True); r.add_argument('--logical-count', type=int, required=True); r.add_argument('--micro-count', type=int, required=True); r.add_argument('--output', required=True)
    return p


def main() -> None:
    args = parser().parse_args()
    if args.command == 'score':
        score_micro(args)
    else:
        recombine_one(args)


if __name__ == '__main__':
    main()
