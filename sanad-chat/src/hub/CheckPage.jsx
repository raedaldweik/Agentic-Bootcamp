// Acceptance check, at /?check. It asks the storyline's questions as each role at the
// right shop time, then questions that are not in the storyline, through the same public
// API the chat uses, and reports for each one how it was answered, how long it took and
// anything that looks wrong. Run it once after a deploy; "Copy report" gives a text
// version to share. Each run makes real model calls when the server has a key.
import { useCallback, useEffect, useRef, useState } from 'react';
import Icon from './Icon';
import * as api from '../lib/hubApi';

const M = { 1: '2026-10-28 09:30', 2: '2026-10-28 11:30', 3: '2026-10-28 12:15', 4: '2026-10-28 13:30', 5: '2026-10-28 16:00', 6: '2026-10-29 10:00' };
// [role, shop time, question, card expected, what the answer must mention (a word, or any one of a group)]
const STORY = [
  ['manager', M[1], 'Show me the status of all the engines.', 'engine_status', ['ENG-204']],
  ['manager', M[1], 'What is the primary risk to ENG-204?', 'delivery_risk', ['P-4582']],
  ['manager', M[1], 'What has changed on ENG-204 since yesterday?', 'forecast_changes', [['36', '5 Nov']]],
  ['manager', M[1], 'Generate a recovery plan for component P-4582.', 'recovery_plan', [['2,400', '2400', 'option B']]],
  ['manager', M[2], 'Has the recovery option been approved?', 'recovery_plan', ['EXQ-0592']],
  ['technician', M[3], 'I need to start the fan blade removal task. Please guide me.', 'job_card', ['JC-FAN-204']],
  ['technician', M[3], 'Can I start fan blade removal now?', 'task_readiness', ['T-117']],
  ['technician', M[3], 'Which tools does this step need?', 'task_tools', ['T-117']],
  ['supervisor', M[3], 'Where is tool T-117?', 'tool_location', ['Gate 3']],
  ['supervisor', M[3], 'Is the tool still at Gate 3?', 'tool_location', [['camera', 'sighting', 'not confirmed', 'custody']]],
  ['technician', M[4], 'T-117 is checked in at Gate 1 and the supervisor has released the work. Guide me through the fan blade removal step by step.', 'job_card', ['step']],
  ['supervisor', M[5], 'Can I approve a deviation so the work can continue?', 'approval_authority', [['Engineering', 'Quality']]],
  ['supervisor', M[6], 'What is now the best way to protect the committed delivery date?', 'protect_delivery', []],
  ['manager', M[6], 'Show me the updated engine status and recovery progress.', 'engine_status', [['16:30', '90 min', 'on track']]],
];
const OFF_SCRIPT = [
  ['manager', M[1], 'Which engine is furthest ahead of its commitment, and by how much?', null, ['ENG-209']],
  ['supervisor', M[2], 'What if P-4582 arrives four hours later than promised?', 'simulate_schedule', []],
  ['supervisor', M[1], 'What does the tool control procedure say about camera detections?', null, [['TC-003', 'Tool Control Procedure']]],
  ['technician', M[5], 'What is the scratch limit in zone B and what did we measure?', null, ['0.25', ['0.8', '0.80']]],
  ['manager', M[6], 'Which approvals were recorded for ENG-204, and by whom?', null, ['EXQ-0592']],
  ['manager', M[1], 'Draw a chart of hours late or ahead for each engine.', 'chart_1', []],
  ['supervisor', M[1], 'Raise a handover request for T-117.', null, ['THR-']],
  ['supervisor', M[5], 'Approve the deviation for the blade finding.', null, [['cannot', "can't", 'can not', 'unable', 'not able', 'only an authorised']]],
  ['technician', M[3], 'Confirm step 1 of the job card.', null, [['released', 'release']]],
  ['manager', M[1], "how's 215 looking", null, ['ENG-215']],
  ['manager', M[1], "What's the weather in Abu Dhabi today?", null, []],
];
const SLOW_S = 15;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const secs = (v) => (v == null ? 'n/a' : `${v.toFixed(1)} s`);
const median = (xs) => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : null; };

async function runOne([role, shopTime, question, card, words], live) {
  const t0 = performance.now();
  let sub;
  try {
    sub = await api.ask({ content: question, persona: role, shopTime });
  } catch (e) {
    if (e.status !== 429) throw e;
    await sleep(8000);
    sub = await api.ask({ content: question, persona: role, shopTime });
  }
  let first = null;
  let result = null;
  while (!result) {
    await sleep(150);
    const st = await api.getStatus(sub.queryId);
    if (st.done) { result = st.result; break; }
    if (first == null && st.text) first = (performance.now() - t0) / 1000;
    if (performance.now() - t0 > 150000) { result = { answer: '', mode: 'timeout', cards: [], followups: [], notice: 'no answer in 150 s' }; }
  }
  const total = (performance.now() - t0) / 1000;
  const answer = result.answer || result.errorText || '';
  const low = answer.toLowerCase();
  const cards = (result.cards || []).map((c) => c.id);
  const issues = [];
  if (live && result.mode !== 'model') issues.push(`answered from shop data, not the model (${result.notice || result.mode})`);
  if (card && !cards.includes(card)) issues.push(`expected card ${card}, got ${cards.join(', ') || 'none'}`);
  if (answer.includes('[[')) issues.push('marker left in the answer');
  const missing = words.filter((w) => !(Array.isArray(w) ? w : [w]).some((x) => low.includes(x.toLowerCase())));
  if (missing.length) issues.push(`answer does not mention ${missing.map((w) => (Array.isArray(w) ? w[0] : w)).join(', ')}`);
  if (total > SLOW_S) issues.push(`slow: ${total.toFixed(1)} s`);
  if (result.mode === 'model' && !(result.followups || []).length) issues.push('no next questions');
  return { role, shopTime, question, mode: result.mode, first, total, cards, answer, issues };
}

export default function CheckPage({ health }) {
  const live = !!health.llm;
  const cases = live ? [...STORY, ...OFF_SCRIPT] : STORY;
  const [rows, setRows] = useState([]);
  const [state, setState] = useState('idle');           // idle · running · done · failed
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  const stopRef = useRef(false);

  const run = useCallback(async () => {
    stopRef.current = false;
    setRows([]);
    setError(null);
    setState('running');
    try {
      for (const c of cases) {
        if (stopRef.current) break;
        const row = await runOne(c, live);
        setRows((r) => [...r, row]);
      }
      setState('done');
    } catch (e) {
      setError(e.message);
      setState('failed');
    }
  }, [live]);                                           // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { stopRef.current = true; }, []);

  const problems = rows.flatMap((r) => r.issues.map((i) => `${r.question.slice(0, 60)}: ${i}`));
  const summary = rows.length
    ? `${rows.length} of ${cases.length} questions. Complete answer: median ${secs(median(rows.map((r) => r.total)))}, slowest ${secs(Math.max(...rows.map((r) => r.total)))}.`
      + (rows.some((r) => r.first != null) ? ` First words: median ${secs(median(rows.filter((r) => r.first != null).map((r) => r.first)))}.` : '')
    : '';
  const report = [
    `Sanad MRO Intelligence Hub acceptance check, ${new Date().toISOString()}`,
    `${window.location.origin}: build ${health.build}, model ${health.model || 'NOT CONFIGURED'}, effort ${health.effort || 'n/a'}, features ${JSON.stringify(health.features || {})}`,
    '',
    ...rows.map((r) => `[${r.issues.length ? '!!' : 'ok'}] ${r.role} ${r.shopTime.slice(5)}  ${r.question}\n     ${r.mode}, first words ${secs(r.first)}, complete ${secs(r.total)}, card ${r.cards.join(', ') || 'none'}\n     ${r.answer.replace(/\s+/g, ' ').slice(0, 260)}${r.issues.map((i) => `\n     -> ${i}`).join('')}`),
    '',
    summary,
    problems.length ? `${problems.length} thing(s) to look at:\n${problems.map((p) => `  - ${p}`).join('\n')}` : 'Nothing to look at.',
  ].join('\n');
  const copy = async () => {
    try { await navigator.clipboard.writeText(report); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* the text is selectable below */ }
  };

  return (
    <div className="hub-check">
      <div className="glass-card hub-check-card">
        <header className="hub-check-head">
          <div className="min-w-0 flex-1">
            <h2>Acceptance check</h2>
            <p>
              {live
                ? `Asks ${cases.length} questions: the storyline as each role, then questions that are not in it. Model ${health.model}, effort ${health.effort}. It makes real model calls and takes a few minutes.`
                : 'No model key is configured on the server, so only the 14 storyline questions run, answered from the shop data.'}
            </p>
          </div>
          {state === 'running'
            ? <button className="hub-btn" onClick={() => { stopRef.current = true; }}>Stop</button>
            : <button className="hub-btn is-primary" onClick={run}>{rows.length ? 'Run again' : 'Run the check'}</button>}
          {rows.length > 0 && <button className="hub-btn" onClick={copy}>{copied ? 'Copied' : 'Copy report'}</button>}
          <a className="hub-btn" href={window.location.pathname}>Open the chat</a>
        </header>

        <div className="hub-check-body">
          {state === 'idle' && <div className="hub-empty"><Icon name="clipboard" size={26} /><p>Ready when you are.</p><span>Nothing has been asked yet.</span></div>}
          {rows.map((r, i) => (
            <div key={i} className={`hub-check-row ${r.issues.length ? 'has-issue' : ''}`}>
              <Icon name={r.issues.length ? 'alert' : 'check'} size={16} style={{ color: r.issues.length ? 'var(--amber)' : 'var(--green)', flex: 'none', marginTop: 2 }} />
              <div className="min-w-0 flex-1">
                <div className="hub-check-q">{r.question}</div>
                <div className="hub-check-meta">
                  {r.role} · shop time {r.shopTime.slice(5)} · {r.mode === 'model' ? 'model' : r.mode === 'direct' ? 'shop data' : r.mode}
                  {' '}· first words {secs(r.first)} · complete {secs(r.total)} · card {r.cards.join(', ') || 'none'}
                </div>
                <div className="hub-check-a">{r.answer.replace(/\s+/g, ' ').slice(0, 300)}</div>
                {r.issues.map((x) => <div key={x} className="hub-check-issue">{x}</div>)}
              </div>
            </div>
          ))}
          {state === 'running' && <div className="hub-step-line is-running" style={{ padding: '10px 4px' }}><span className="hub-spinner" /><span>Asking question {rows.length + 1} of {cases.length}</span></div>}
          {error && <div className="hub-line is-error" style={{ margin: '8px 0' }}>The check stopped: {error}</div>}
        </div>

        {rows.length > 0 && (
          <footer className="hub-check-foot">
            <b>{summary}</b>
            <span style={{ color: problems.length ? 'var(--amber)' : 'var(--green)' }}>
              {state !== 'done' ? '' : problems.length ? `${problems.length} thing(s) to look at.` : 'Nothing to look at.'}
            </span>
          </footer>
        )}
      </div>
    </div>
  );
}
