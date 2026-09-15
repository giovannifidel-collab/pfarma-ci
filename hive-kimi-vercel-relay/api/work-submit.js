const TASK_ID = 'HIVE-KIMI-WORK-0002';
const LAB_TOKEN = 'HIVE-KIMI-WORK-LAB-20260828-V1';
const EXPECTED_ANSWER = '21246';

export default function handler(req, res) {
  if (req.method !== 'GET') {
    res.status(405).json({ ok: false, error: 'method not allowed' });
    return;
  }

  const token = String(req.query.token || '');
  const taskId = String(req.query.task_id || '');
  const answer = String(req.query.answer || '');

  if (token !== LAB_TOKEN) {
    console.warn('HIVE_KIMI_WORK_REJECT', { taskId, answer, reason: 'bad_token' });
    res.status(403).json({ ok: false, accepted: false, error: 'invalid lab token' });
    return;
  }

  if (taskId !== TASK_ID) {
    console.warn('HIVE_KIMI_WORK_REJECT', { taskId, answer, reason: 'bad_task_id' });
    res.status(400).json({ ok: false, accepted: false, error: 'invalid task id' });
    return;
  }

  const correct = answer === EXPECTED_ANSWER;
  console.log('HIVE_KIMI_WORK_RESULT', JSON.stringify({
    task_id: taskId,
    answer,
    correct,
    user_agent: req.headers['user-agent'] || null,
    at: new Date().toISOString()
  }));

  res.setHeader('Cache-Control', 'no-store');
  res.status(200).json({
    ok: true,
    accepted: true,
    task_id: taskId,
    answer,
    correct,
    certified: correct,
    message: correct ? 'HIVE KIMI WORK ROUNDTRIP READY' : 'answer received but incorrect'
  });
}
