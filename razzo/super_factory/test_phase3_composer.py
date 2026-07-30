import json
from pathlib import Path
import pytest
from razzo.super_factory.phase3_composer import compose

SHA='a'*40
RSH='b'*40

def fixture(tmp_path:Path):
    queue={'items':[{'work_item_id':'w1','execution_id':'e1','project_id':'p','generation_id':'g','input_sha':SHA,'collision_domain':'d1','idempotency_key':'i1'}]}
    leases={'leases':[{'work_item_id':'w1','execution_id':'e1','shard':'razzo-shard-0001','run_id':1,'collision_domain':'d1','idempotency_key':'i1','state':'COMPLETED'}]}
    folder=tmp_path/'e1'; folder.mkdir(); (folder/'e1.json').write_text(json.dumps({'status':'HEALTHY','verification_state':'DISPATCH_ENVELOPE_VERIFIED','exact_sha':RSH}))
    return queue,leases

def test_compose_verified_generation(tmp_path):
    q,l=fixture(tmp_path); result=compose(q,l,tmp_path)
    assert result['work_item_count']==1
    assert result['verification_state']=='GENERATION_RECEIPTS_COMPOSED'
    assert len(result['composition_sha256'])==64

def test_missing_completed_lease_fails(tmp_path):
    q,_=fixture(tmp_path)
    with pytest.raises(ValueError,match='missing completed lease'): compose(q,{'leases':[]},tmp_path)

def test_invalid_receipt_fails(tmp_path):
    q,l=fixture(tmp_path); (tmp_path/'e1'/'e1.json').write_text('{}')
    with pytest.raises(ValueError,match='invalid receipt'): compose(q,l,tmp_path)

def test_collision_overlap_fails(tmp_path):
    q,l=fixture(tmp_path)
    q['items'].append({**q['items'][0],'work_item_id':'w2','execution_id':'e2','idempotency_key':'i2'})
    l['leases'].append({**l['leases'][0],'work_item_id':'w2','execution_id':'e2','idempotency_key':'i2','shard':'razzo-shard-0002'})
    folder=tmp_path/'e2'; folder.mkdir(); (folder/'e2.json').write_text(json.dumps({'status':'HEALTHY','verification_state':'DISPATCH_ENVELOPE_VERIFIED','exact_sha':RSH}))
    with pytest.raises(ValueError,match='collision domains'): compose(q,l,tmp_path)
