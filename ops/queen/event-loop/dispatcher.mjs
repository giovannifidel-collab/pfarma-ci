#!/usr/bin/env node

const SUPPORTED = new Set([
  'queen.task.requested',
  'fabric.result.ready',
  'verification.result.ready',
  'school.experience.verified',
  'world.state.changed',
  'queen.cycle.continue'
]);

function fail(message, code = 1) {
  console.error(`EVENT_DISPATCH_FAIL=${message}`);
  process.exit(code);
}

function parseEvent() {
  const raw = process.env.HIVE_EVENT_JSON || process.argv[2];
  if (!raw) fail('missing_event', 10);
  try {
    return JSON.parse(raw);
  } catch {
    fail('invalid_json', 11);
  }
}

function validate(evt) {
  if (!evt || typeof evt !== 'object') fail('invalid_event', 12);
  if (evt.version !== '1') fail('unsupported_version', 13);
  if (!evt.id || typeof evt.id !== 'string') fail('missing_id', 14);
  if (!evt.type || !SUPPORTED.has(evt.type)) fail('unsupported_type', 15);
  if (!evt.source || typeof evt.source !== 'string') fail('missing_source', 16);
  if (!evt.occurred_at || Number.isNaN(Date.parse(evt.occurred_at))) fail('invalid_occurred_at', 17);
  if (!evt.payload || typeof evt.payload !== 'object' || Array.isArray(evt.payload)) fail('invalid_payload', 18);
}

function route(evt) {
  const base = {
    accepted: true,
    event_id: evt.id,
    event_type: evt.type,
    source: evt.source,
    processed_at: new Date().toISOString()
  };

  switch (evt.type) {
    case 'queen.task.requested':
      return { ...base, action: 'fabric.execute', next_event: 'fabric.result.ready' };
    case 'fabric.result.ready':
      return { ...base, action: 'verification.execute', next_event: 'verification.result.ready' };
    case 'verification.result.ready':
      return evt.payload?.verified === true
        ? { ...base, action: 'school.record_verified_experience', next_event: 'school.experience.verified' }
        : { ...base, action: 'queen.replan', next_event: 'queen.cycle.continue' };
    case 'school.experience.verified':
      return { ...base, action: 'world.update', next_event: 'world.state.changed' };
    case 'world.state.changed':
      return { ...base, action: 'queen.evaluate_goals', next_event: 'queen.cycle.continue' };
    case 'queen.cycle.continue':
      return { ...base, action: 'queen.cognitive_cycle', next_event: null };
    default:
      fail('unreachable', 19);
  }
}

const evt = parseEvent();
validate(evt);
const result = route(evt);
console.log(JSON.stringify(result));
