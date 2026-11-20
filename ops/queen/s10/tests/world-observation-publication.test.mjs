import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {decideWorldSnapshotPublication as decide} from '../world-observation-publication.mjs';
const now=Date.parse('2026-11-19T09:00:00Z');
const format=ms=>new Date(ms).toISOString().replace('.000Z','Z');
const valid=(time,fingerprint='a'.repeat(64))=>({
 schema_version:1,policy:'authoritative-source-first',generated_at:format(time),
 state_fingerprint:fingerprint,projects:{hive:{source:{available:true,sha:'b'.repeat(40)}}}
});
const before=(age=15*60*1000)=>valid(now-age);
const current=()=>valid(now-5000);

test('unchanged semantic fingerprint and valid new 15m observation is heartbeat, NOT S1 wake',()=>{
 const d=decide(before(),current(),{nowMs:now});
 assert.equal(d.status,'HEARTBEAT');
 assert.equal(d.observation_recorded,true);
 assert.equal(d.semantic_changed,false);
});

test('genuine semantic source change is the ONLY existing S1 wake',()=>{
 const d=decide(before(),valid(now-5000,'c'.repeat(64)),{nowMs:now});
 assert.equal(d.status,'SEMANTIC');
 assert.equal(d.semantic_changed,true);
 assert.equal(d.observation_recorded,true);
});

test('short-interval same semantic observation is safely ignored',()=>{
 const old=valid(now-3*60*1000),newer=valid(now-2*60*1000);
 const d=decide(old,newer,{nowMs:now});
 assert.equal(d.status,'SKIP');
 assert.equal(d.semantic_changed,false);
 assert.equal(d.observation_recorded,false);
});

test('unavailable first World can publish a genuine initial source snapshot only',()=>{
 const d=decide({},current(),{nowMs:now});
 assert.equal(d.status,'SEMANTIC');
 assert.equal(d.semantic_changed,true);
});

test('stale replay, forged future stamp, missing timestamp and invalid fingerprint fail closed',()=>{
 const bad=[
  [before(),before()],
  [before(),valid(now-9*60*1000)],
  [valid(now+120000),current()],
  [before(),valid(now+120000)],
  [before(),{...current(),generated_at:'yesterday'}],
  [before(),{...current(),state_fingerprint:'not-a-hash'}],
  [before(),{...current(),projects:null}],
  [before(),{...current(),schema_version:2}],
  [before(),{...current(),policy:'untrusted'}],
  [{...before(),schema_version:9},current()]
 ];
 for(const [old,source] of bad){
  const d=decide(old,source,{nowMs:now});
  assert.equal(d.status,'DENY');
  assert.equal(d.semantic_changed,false);
  assert.equal(d.observation_recorded,false);
 }
});

test('original existing World workflow has only semantic S1 wake and no extra scheduler',()=>{
 const w=readFileSync('.github/workflows/hive-world-sync.yml','utf8');
 assert.equal((w.match(/name: HIVE Queen Global World Sync/g)||[]).length,1);
 assert.equal((w.match(/^  schedule:/gm)||[]).length,0);
 assert.ok(w.includes('clock_minute:'));
 assert.ok(w.includes('S10_CLOUDFLARE_CLOCK_TICK_METADATA_VALIDATED=PASS'));
 assert.equal((w.match(/event_type:"world-state-changed"/g)||[]).length,1);
 assert.ok(w.includes("if: steps.publish.outputs.changed == 'true'"));
 assert.ok(w.includes('node ops/queen/s10/world-observation-publication.mjs'));
 assert.ok(w.includes('WORLD_OBSERVATION_HEARTBEAT=RECORDED_NO_S1_WAKE'));
 assert.ok(w.includes('WORLD_SEMANTIC_CHANGE=true'));
 assert.equal((w.match(/^  repository_dispatch:/gm)||[]).length,1);
 assert.ok(w.includes('types: [hive_world_clock_tick]'));
});

console.log('S10_WORLD_HEARTBEAT_PURE_DECISION_NEGATIVE_TESTS=PASS');
console.log('S10_WORLD_SEMANTIC_WAKE_ONLY_NO_SECOND_LOOP=TRUE');
