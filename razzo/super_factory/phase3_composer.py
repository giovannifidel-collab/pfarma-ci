#!/usr/bin/env python3
"""Fail-closed composition of one HOMO NOVUS distributed generation."""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
from typing import Any
SHA40=re.compile(r'^[0-9a-f]{40}$')

def load(p:str)->dict[str,Any]: return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def compose(queue:dict[str,Any], leases:dict[str,Any], receipts:Path)->dict[str,Any]:
    completed={}
    seen_idem=set()
    for lease in leases.get('leases',[]):
        if lease.get('state')!='COMPLETED': continue
        wid=str(lease.get('work_item_id','')); idem=str(lease.get('idempotency_key',''))
        if not wid or wid in completed: raise ValueError(f'duplicate completed lease: {wid}')
        if not idem or idem in seen_idem: raise ValueError(f'duplicate idempotency key: {idem}')
        completed[wid]=lease; seen_idem.add(idem)
    outputs=[]; generations=set(); projects=set(); domains=set()
    for item in queue.get('items',[]):
        if item.get('state','QUEUED') not in {'QUEUED','DISPATCHED','COMPLETED'}: continue
        wid=str(item.get('work_item_id','')); lease=completed.get(wid)
        if not lease: raise ValueError(f'missing completed lease: {wid}')
        sha=str(item.get('input_sha',''))
        if not SHA40.fullmatch(sha): raise ValueError(f'invalid exact SHA: {wid}')
        if lease.get('idempotency_key')!=item.get('idempotency_key'): raise ValueError(f'idempotency mismatch: {wid}')
        if lease.get('collision_domain')!=item.get('collision_domain'): raise ValueError(f'collision-domain mismatch: {wid}')
        folder=receipts/str(item['execution_id']); matches=sorted(folder.glob('*.json'))
        if len(matches)!=1: raise ValueError(f'receipt missing or ambiguous: {wid}')
        receipt=json.loads(matches[0].read_text(encoding='utf-8-sig'))
        if receipt.get('status')!='HEALTHY' or receipt.get('verification_state')!='DISPATCH_ENVELOPE_VERIFIED': raise ValueError(f'invalid receipt: {wid}')
        receipt_sha=str(receipt.get('exact_sha',''))
        if not SHA40.fullmatch(receipt_sha): raise ValueError(f'receipt exact SHA missing: {wid}')
        generations.add(str(item['generation_id'])); projects.add(str(item['project_id'])); domains.add(str(item['collision_domain']))
        outputs.append({'work_item_id':wid,'execution_id':item['execution_id'],'input_sha':sha,'shard':lease['shard'],'run_id':lease.get('run_id'),'receipt_exact_sha':receipt_sha,'receipt_file':matches[0].as_posix()})
    if not outputs: raise ValueError('no composable work items')
    if len(generations)!=1 or len(projects)!=1: raise ValueError('composition requires one project and one generation')
    if len(domains)!=len(outputs): raise ValueError('collision domains must be unique within generation')
    outputs.sort(key=lambda x:x['work_item_id'])
    digest=hashlib.sha256(json.dumps(outputs,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'schema':'razzo.homo-novus.composition.v1','project_id':next(iter(projects)),'generation_id':next(iter(generations)),'work_item_count':len(outputs),'verification_state':'GENERATION_RECEIPTS_COMPOSED','composition_sha256':digest,'product_progress':False,'outputs':outputs}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--queue',required=True); p.add_argument('--leases',required=True); p.add_argument('--receipts',required=True); p.add_argument('--out',required=True); a=p.parse_args()
    result=compose(load(a.queue),load(a.leases),Path(a.receipts)); out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8'); print(f"generation={result['generation_id']} composed={result['work_item_count']} sha256={result['composition_sha256']}")
if __name__=='__main__': main()
