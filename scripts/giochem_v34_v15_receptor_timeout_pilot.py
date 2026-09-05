#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TARGETS = ('ALDH1','MTORC1','IDH1')
EXPECTED_SHARDS = {'ALDH1':27,'MTORC1':27,'IDH1':26}
FROZEN_TIMEOUT_SECONDS = 900
EXECUTION_MODE = 'V15_RECEPTOR_SPLIT_PER_DOCKING_TIMEOUT_ONLY_TECHNICAL_PILOT'


def load_modules(source_root: Path):
    scripts = source_root / 'scripts'
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import validation_v34_blind_score_worker as worker
    return worker


def patch_timeout(worker, seconds: int) -> None:
    if seconds <= FROZEN_TIMEOUT_SECONDS:
        raise SystemExit('FAIL-CLOSED timeout must exceed frozen timeout')
    real_run = subprocess.run
    if worker.dev.subprocess.run is not real_run:
        raise SystemExit('FAIL-CLOSED unexpected subprocess hook')
    gnina = str(Path(os.environ.get('GIOCHEM_GNINA_BIN','')).resolve())
    def wrapped(*args, **kwargs):
        cmd = args[0] if args else kwargs.get('args')
        first = str(Path(str(cmd[0])).resolve()) if isinstance(cmd,(list,tuple)) and cmd else ''
        if kwargs.get('timeout') == FROZEN_TIMEOUT_SECONDS and first == gnina:
            kwargs = dict(kwargs); kwargs['timeout'] = seconds
        return real_run(*args, **kwargs)
    worker.dev.subprocess.run = wrapped


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--source-root',required=True); ap.add_argument('--target',required=True,choices=TARGETS)
    ap.add_argument('--blind-input',required=True); ap.add_argument('--receptor-dir',required=True); ap.add_argument('--receptor-manifest',required=True)
    ap.add_argument('--runtime-lock-sha256',required=True); ap.add_argument('--source-code-sha',required=True)
    ap.add_argument('--receptor-index',type=int,required=True,choices=[0,1]); ap.add_argument('--gnina-timeout-seconds',type=int,required=True)
    args=ap.parse_args()
    root=Path(args.source_root).resolve(); worker=load_modules(root)
    policy=json.loads(worker.POLICY.read_text())
    if policy.get('status')!='FROZEN_AFTER_V34_DEVELOPMENT_PASS_AND_METADATA_ONLY_TARGET_SELECTION_BEFORE_ANY_V34_EXTERNAL_SCORE': raise SystemExit('FAIL-CLOSED policy drift')
    if tuple(policy['externalTargetSelection']['targets'])!=TARGETS: raise SystemExit('FAIL-CLOSED target drift')
    runtime=policy['runtime']; exe=Path(os.environ.get('GIOCHEM_GNINA_BIN',''))
    import importlib.metadata
    if importlib.metadata.version('meeko')!=str(runtime['meeko']) or importlib.metadata.version('rdkit')!=str(runtime['rdkit']): raise SystemExit('FAIL-CLOSED runtime package drift')
    if not exe.is_file() or worker.static_helpers.sha256_file(exe)!=runtime['gninaSha256'] or args.runtime_lock_sha256!=runtime['runtimeLockSha256']: raise SystemExit('FAIL-CLOSED runtime lock drift')
    receptors,_=worker.dev.load_receptors(args.target,Path(args.receptor_dir),Path(args.receptor_manifest))
    rows=worker.dev.load_blind(Path(args.blind_input)); n=EXPECTED_SHARDS[args.target]
    logical=[r for r in rows if int(r['blindIndex'])%n==0]
    selected=[r for pos,r in enumerate(logical) if pos%100==0]
    if len(selected)!=1: raise SystemExit(f'FAIL-CLOSED deterministic pilot cardinality {len(selected)}')
    row=selected[0]; idx=int(row['blindIndex']); blind_id=str(row['blindId']); seed=worker.dev.deterministic_seed(args.target,idx,blind_id)
    protocol={'suite':policy['suite'],'version':policy['version'],'docking':policy['docking'],'signals':['cnnaffinity_max','vina_best','cnnscore_mean3']}
    patch_timeout(worker,args.gnina_timeout_seconds)
    from rdkit import Chem
    with tempfile.TemporaryDirectory(prefix=f'giochem-v34-v15-{args.target}-r{args.receptor_index}-') as td:
        work=Path(td); mol=Chem.MolFromSmiles(str(row['smiles']))
        if mol is None: raise SystemExit('FAIL-CLOSED RDKit parse')
        sdf=work/'ligand.sdf'; pdbqt=work/'ligand.pdbqt'
        worker.dev.v2.write_ligand_sdf(mol,sdf,seed)
        worker.dev.v33_helpers.prepare_ligand_with_macrocycle_fallback(sdf,pdbqt,work)
        try:
            worker.dev.score_receptor(exe,receptors[args.receptor_index],pdbqt,seed,work,f'receptor{args.receptor_index+1}',protocol)
        except subprocess.TimeoutExpired:
            print(json.dumps({'target':args.target,'receptorIndex':args.receptor_index,'status':'TIMEOUT','timeoutSeconds':args.gnina_timeout_seconds,'executionMode':EXECUTION_MODE},sort_keys=True))
            raise SystemExit(4)
        except Exception as exc:
            print(json.dumps({'target':args.target,'receptorIndex':args.receptor_index,'status':'TECHNICAL_ERROR','errorType':type(exc).__name__,'executionMode':EXECUTION_MODE},sort_keys=True))
            raise SystemExit(5)
        finally:
            for p in work.glob('receptor*'):
                try: p.unlink()
                except Exception: pass
        print(json.dumps({'target':args.target,'receptorIndex':args.receptor_index,'status':'OK','executionMode':EXECUTION_MODE,'truthRead':False,'scorePersisted':False},sort_keys=True))

if __name__=='__main__': main()
