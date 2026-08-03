from __future__ import annotations
import hashlib, tempfile, unittest
from pathlib import Path
from .prelaunch import *

SHA='a'*40; CAND='b'*40; OBJ='c'*64; WAVE='d'*64

def contract():
    return RepositoryContract('pfarma-cloud','giovannifidel-collab/pfarma-cloud','integration/razzo',SHA,('api/**','tests/**'),('.github/**','secrets/**','migrations/**'),('python -m unittest tests.test_safe',),'product-ci','robot-qa','delete candidate branch and restore journal',3)

def unit(i, domain, path):
    b=PatchBundle(f'B{i}',OBJ,SHA,CAND,(path,),(),120,contract().focused_test_commands,('assert user outcome',),hashlib.sha256(path.encode()).hexdigest())
    e=ExactHeadReceipt(OBJ,f'B{i}',CAND,CAND,CAND,CAND,'product-ci','robot-qa',(path,),('assert user outcome',))
    return WorkUnitReceipt(f'U{i}',domain,b,e)

class PrelaunchTests(unittest.TestCase):
    def test_provider_modes(self):
        p=ProviderContract('chatgpt-connected',ProviderState.VERIFIED_INTERACTIVE,True,True,True,False,False,('PR 750 created through connected GitHub',))
        self.assertTrue(p.pilot_eligible); self.assertFalse(p.continuous_eligible)
        with self.assertRaises(ValueError): ProviderContract('bad',ProviderState.VERIFIED_UNATTENDED,True,True,True,False,False,('x',)).validate()
    def test_repository_contract(self): contract().validate()
    def test_contract_rejects_overlap(self):
        c=RepositoryContract('p','o/r','lane',SHA,('api/**',),('api/private/**',),('x',),'a','b','r')
        with self.assertRaises(ValueError): c.validate()
    def test_patch_security(self): unit(1,'api/a','api/a.py').validate(contract())
    def test_patch_rejects_forbidden(self):
        b=PatchBundle('B',OBJ,SHA,CAND,('.github/workflows/x.yml',),(),12,contract().focused_test_commands,('x',),'e'*64)
        with self.assertRaises(ValueError): b.validate(contract())
    def test_patch_rejects_traversal(self):
        b=PatchBundle('B',OBJ,SHA,CAND,('api/../secret',),(),12,contract().focused_test_commands,('x',),'e'*64)
        with self.assertRaises(ValueError): b.validate(contract())
    def test_exact_head(self): unit(1,'api/a','api/a.py').exact_head.validate(contract())
    def test_exact_head_rejects_stale(self):
        e=ExactHeadReceipt(OBJ,'B',CAND,CAND,'f'*40,CAND,'product-ci','robot-qa',('api/a.py',),('x',))
        with self.assertRaises(ValueError): e.validate(contract())
    def test_aggregate_multiworkstream(self):
        a=AggregateReceipt(WAVE,OBJ,(unit(1,'api/a','api/a.py'),unit(2,'tests/b','tests/b.py')),2,1,3); a.validate(contract())
    def test_aggregate_rejects_collision(self):
        a=AggregateReceipt(WAVE,OBJ,(unit(1,'same','api/a.py'),unit(2,'same','tests/b.py')),2,0,0)
        with self.assertRaises(ValueError): a.validate(contract())
    def test_atomic_journal_cas_and_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            store=AtomicJournalStore(Path(d)/'journal.json')
            store.compare_and_swap(-1,JournalSnapshot(0,OBJ,'QUEUED',[{'e':1}]))
            recovered=AtomicJournalStore(Path(d)/'journal.json').load()
            self.assertEqual(recovered.state,'QUEUED')
            with self.assertRaises(JournalConflict): store.compare_and_swap(-1,JournalSnapshot(0,OBJ,'BAD'))
            store.compare_and_swap(0,JournalSnapshot(1,OBJ,'RUNNING',recovered.events+[{'e':2}]))
            self.assertEqual(AtomicJournalStore(Path(d)/'journal.json').load().generation,1)
    def test_file_lease_collision_expiry_release(self):
        with tempfile.TemporaryDirectory() as d:
            a=FileLease(d,'domain/api','owner-a',10); b=FileLease(d,'domain/api','owner-b',10)
            a.acquire(now=100)
            with self.assertRaises(JournalConflict): b.acquire(now=101)
            b.acquire(now=111); b.release(); self.assertFalse(b.path.exists())
    def test_rollback(self): RollbackPlan(OBJ,'razzo/o/abc',CAND,True,True,('domain/api',),4).validate()
    def test_activation_gate_blocks_continuous_provider(self):
        p=ProviderContract('chatgpt-connected',ProviderState.VERIFIED_INTERACTIVE,True,True,True,False,False,('evidence',))
        a=AggregateReceipt(WAVE,OBJ,(unit(1,'api/a','api/a.py'),unit(2,'tests/b','tests/b.py')),2,0,0)
        e=ActivationEvidence(p,contract(),a,True,True,True,True,True,0,True)
        self.assertTrue(e.evaluate(continuous=False).ready)
        self.assertFalse(e.evaluate(continuous=True).ready)
    def test_activation_gate_lists_missing(self):
        p=ProviderContract('p',ProviderState.PENDING,False,False,False,False,False)
        e=ActivationEvidence(p,contract(),None,False,False,False,False,False,1,False)
        r=e.evaluate(continuous=True); self.assertFalse(r.ready); self.assertGreaterEqual(len(r.missing),8)

if __name__=='__main__': unittest.main()
