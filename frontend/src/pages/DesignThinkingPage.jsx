import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useApp } from '../context/AppContext';
import { getDesignState, resetDesign, streamDesignChat } from '../services/api';

/* The Design Thinking Agent: one conversation that builds a population-health agent on SAS Viya,
   data, model, decision, agent. The steps are staged by the backend (services/design_studio.py)
   and shown here as the tool calls the live agent makes; the words are the model's. */

const STAGES = [
  { id: 'idea', n: 1, title: 'The idea', product: 'Design thinking', sub: 'The decision the agent supports' },
  { id: 'data', n: 2, title: 'The data', product: 'SAS Viya · CAS', sub: 'A promoted patient table in Public' },
  { id: 'model', n: 3, title: 'The model', product: 'Model Studio · Model Manager', sub: 'AutoML champion, registered, published' },
  { id: 'decision', n: 4, title: 'The decision', product: 'Intelligent Decisioning', sub: 'Outreach rules on the risk, published' },
  { id: 'agent', n: 5, title: 'The agent', product: 'Retrieval Agent Manager', sub: 'Table, model and decision as tools' },
];

const OPENERS = [
  { label: 'Diabetes deterioration', text: 'I want a population health agent for people with diabetes who are at risk of deterioration, so the care team knows who to contact first.' },
  { label: 'Who to call first', text: 'Build me an agent for our diabetes registry that tells the care coordinators which patients to call this week and why.' },
];

const STATUS_TONE = { creating: 'busy', training: 'busy', promoted: 'ok', registered: 'ok', published: 'ok', locked: 'ok', champion: 'ok', ready: 'ok' };
const PRIORITY_TONE = { High: 'red', Medium: 'amber', Low: 'blue', Routine: 'green' };

const md = {
  p: (p) => <p className="my-1 leading-[1.7]" {...p} />,
  strong: (p) => <strong style={{ color: 'var(--brand)', fontWeight: 700 }} {...p} />,
  em: (p) => <em style={{ color: 'var(--brand-lo)' }} {...p} />,
  ul: (p) => <ul className="my-1.5 space-y-0.5 pl-5 list-disc" {...p} />,
  ol: (p) => <ol className="my-1.5 space-y-0.5 pl-5 list-decimal" {...p} />,
  li: (p) => <li className="leading-[1.65]" {...p} />,
  code: (p) => <code className="px-1 py-0.5 rounded text-[12px]" style={{ background: 'rgba(43,83,120,0.08)', color: 'var(--brand)' }} {...p} />,
  h1: (p) => <p className="font-bold my-1" {...p} />, h2: (p) => <p className="font-bold my-1" {...p} />, h3: (p) => <p className="font-bold my-1" {...p} />,
};

// Conversations survive a tab switch (the page unmounts) but not a reload: the backend keeps the build state.
const STORE = {};
function sessionId(teamId) {
  const key = `design_sid_${teamId || 'solo'}`;
  try {
    let v = sessionStorage.getItem(key);
    if (!v) { v = `${teamId || 'solo'}-${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36)}`; sessionStorage.setItem(key, v); }
    return v;
  } catch { return `${teamId || 'solo'}-mem`; }
}

const fmtPct = (x, d = 1) => `${(100 * x).toFixed(d)}%`;
const fmtInt = (n) => Number(n).toLocaleString();

export default function DesignThinkingPage() {
  const { team } = useApp();
  const sid = sessionId(team?.id);
  const [messages, setMessages] = useState(() => STORE[sid]?.messages || []);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [activeStage, setActiveStage] = useState(null);
  const [state, setState] = useState({ done: [], artefacts: [] });
  const [mode, setMode] = useState(null);
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => { STORE[sid] = { messages }; }, [sid, messages]);
  useEffect(() => { getDesignState(sid).then(setState).catch(() => {}); }, [sid]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [messages, busy]);

  const patchLast = (fn) => setMessages((m) => m.map((x, i) => (i === m.length - 1 ? fn(x) : x)));

  const send = async (text) => {
    const q = (text ?? input).trim();
    if (!q || busy) return;
    setInput('');
    setBusy(true);
    setMessages((m) => [...m.map((x) => ({ ...x, next: undefined })),
      { role: 'user', content: q },
      { role: 'assistant', intro: '', items: [], text: '', done: false }]);
    abortRef.current?.abort();
    const ctl = new AbortController(); abortRef.current = ctl;
    let acc = '';
    try {
      await streamDesignChat({ sessionId: sid, message: q }, (ev) => {
        switch (ev.type) {
          case 'meta':
            setMode({ mode: ev.mode, model: ev.model });
            setActiveStage(ev.stage);
            patchLast((x) => ({ ...x, mode: ev.mode, model: ev.model }));
            break;
          case 'intro':
            patchLast((x) => ({ ...x, intro: ev.text }));
            break;
          case 'step':
            patchLast((x) => {
              const items = [...x.items];
              const i = items.findIndex((it) => it.kind === 'step' && it.id === ev.id);
              const step = { kind: 'step', id: ev.id, tool: ev.tool, args: ev.args, status: ev.status, result: ev.result, ms: ev.ms, log: ev.log,
                progress: i >= 0 ? items[i].progress : null };
              if (i >= 0) items[i] = step; else items.push(step);
              return { ...x, items };
            });
            break;
          case 'progress':
            patchLast((x) => ({ ...x, items: x.items.map((it) => (it.kind === 'step' && it.id === ev.id ? { ...it, progress: { label: ev.label, pct: ev.pct } } : it)) }));
            break;
          case 'block':
            patchLast((x) => ({ ...x, items: [...x.items, { kind: 'block', block: ev.block }] }));
            break;
          case 'artefact':
            setState((s) => {
              const arts = [...(s.artefacts || [])];
              const i = arts.findIndex((a) => a.id === ev.artefact.id);
              if (i >= 0) arts[i] = ev.artefact; else arts.push(ev.artefact);
              return { ...s, artefacts: arts };
            });
            break;
          case 'delta':
            acc += ev.text;
            patchLast((x) => ({ ...x, text: acc }));
            break;
          case 'final':
            patchLast((x) => ({ ...x, text: ev.text || acc, done: true, next: ev.next || [] }));
            if (ev.state) setState(ev.state);
            break;
          case 'error':
            patchLast((x) => ({ ...x, done: true, error: ev.text }));
            break;
          default:
        }
      }, ctl.signal);
    } catch (e) {
      if (e.name !== 'AbortError') patchLast((x) => ({ ...x, done: true, error: `Connection error: ${e.message}` }));
    }
    patchLast((x) => ({ ...x, done: true }));
    setBusy(false);
    setActiveStage(null);
    inputRef.current?.focus();
  };

  const startOver = async () => {
    abortRef.current?.abort();
    setBusy(false);
    setMessages([]);
    try { const s = await resetDesign(sid); setState(s); } catch { setState({ done: [], artefacts: [] }); }
  };

  const doneStages = new Set(state.done || []);
  const last = messages[messages.length - 1];

  return (
    <div className="h-full flex gap-4 p-4 pt-3">
      {/* Left rail: the path and what now exists on Viya */}
      <div className="w-[262px] shrink-0 flex flex-col gap-3 min-h-0">
        <div className="glass-card p-3.5 shrink-0">
          <p className="panel-title mb-0.5">The path</p>
          <p className="text-[9.5px] mb-2.5" style={{ color: 'var(--text-faint)' }}>One conversation, four things built on SAS Viya</p>
          <ol className="triad-list">
            {STAGES.map((st) => {
              const isActive = busy && activeStage === st.id;
              const isDone = doneStages.has(st.id);
              return (
                <li key={st.id} className={`triad-stage ${isActive ? 'active' : ''} ${isDone || isActive ? 'lit' : ''}`}>
                  <span className="triad-n">{isDone && !isActive ? '✓' : st.n}</span>
                  <span className="triad-body">
                    <span className="triad-title">{st.title}<em>{st.product}</em></span>
                    <span className="triad-sub">{st.sub}</span>
                  </span>
                  {isActive && <span className="triad-pulse" />}
                </li>
              );
            })}
          </ol>
        </div>

        <div className="glass-card p-3.5 flex-1 min-h-0 flex flex-col">
          <p className="panel-title mb-0.5">On SAS Viya</p>
          <p className="text-[9.5px] mb-2" style={{ color: 'var(--text-faint)' }}>{state.artefacts?.length ? `${state.artefacts.length} artefact${state.artefacts.length === 1 ? '' : 's'} this session` : 'Nothing built yet'}</p>
          <div className="flex-1 overflow-y-auto min-h-0 ds-artefacts">
            {(state.artefacts || []).map((a) => (
              <div key={a.id} className="ds-artefact">
                <div className="ds-art-kind">{a.kind}</div>
                <div className="ds-art-name">{a.name}</div>
                <div className="ds-art-row">
                  <span className={`ds-status ${STATUS_TONE[a.status] || ''}`}>{a.status}</span>
                  {a.detail && <span className="ds-art-detail">{a.detail}</span>}
                </div>
                <div className="ds-art-where">{a.where}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* The conversation */}
      <div className="flex-1 glass-card flex flex-col relative min-w-0" style={{ boxShadow: 'var(--glass-shadow-lg)' }}>
        <img src="/sas-logo.png" alt="" className="chat-watermark" />
        <div className="flex items-center justify-between gap-3 px-6 py-3 border-b border-[rgba(15,23,42,0.07)] relative z-[5]">
          <div className="flex items-center gap-2 min-w-0">
            <span className="w-[3px] h-4 rounded shrink-0" style={{ background: 'var(--brand-grad)' }} />
            <div className="min-w-0">
              <div className="text-sm font-bold truncate" style={{ color: 'var(--text)' }}>Design Thinking Agent</div>
              <div className="text-[10.5px] truncate" style={{ color: 'var(--text-dim)' }}>
                Population Health Builder · SAS Viya MCP server · 32 tools
                {team?.environment ? ` · ${team.environment.name || 'Environment ' + team.environment.id}` : ''}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {mode && (
              <span className="ds-mode" title={mode.mode === 'live' ? 'The narration is written by the model from the facts of each step' : 'No model key: a template narrates the same facts'}>
                <i className={mode.mode === 'live' ? 'live' : ''} />
                {mode.mode === 'live' ? `Narration · ${mode.model}` : 'Scripted narration'}
              </span>
            )}
            {messages.length > 0 && (
              <button className="ds-ghost" onClick={startOver} title="Forget this build and begin again">Start over</button>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 relative z-[2] ds-thread">
          {messages.length === 0 && (
            <div className="ds-hero animate-fade-up">
              <div className="ds-hero-kicker">Design thinking, built live</div>
              <h2 className="ds-hero-title">Tell me what you want to build.</h2>
              <p className="ds-hero-sub">I restate the decision, then build it on SAS Viya in four steps you can watch: the <b>data</b> as a table in CAS, the <b>model</b> in Model Studio, the <b>decision</b> in Intelligent Decisioning, and the <b>agent</b> in RAM.</p>
              <div className="flex flex-wrap gap-2 mt-3">
                {OPENERS.map((o) => (
                  <button key={o.label} className="suggestion-chip" onClick={() => send(o.text)}>
                    <span className="chip-tag">IDEA</span>{o.label}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (m.role === 'user'
            ? <div key={i} className="flex justify-end mb-3 animate-fade-up"><div className="msg-user-bubble px-4 py-2.5 text-[13px] max-w-[70%]" style={{ color: 'var(--text)' }}>{m.content}</div></div>
            : <AssistantMessage key={i} m={m} isLast={i === messages.length - 1} busy={busy} onChip={send} />))}
          <div ref={endRef} />
        </div>

        <form className="ds-input relative z-[5]" onSubmit={(e) => { e.preventDefault(); send(); }}>
          <input ref={inputRef} value={input} onChange={(e) => setInput(e.target.value)} disabled={busy}
            placeholder={messages.length ? 'Say what to do next, or ask a question…' : 'Describe the agent you want, in your own words…'} />
          <button type="submit" disabled={busy || !input.trim()} aria-label="Send">
            {busy ? <span className="ds-spin" /> : (
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}

function AssistantMessage({ m, isLast, busy, onChip }) {
  const hasBody = m.intro || m.items.length || m.text;
  return (
    <div className="mb-3 animate-fade-up max-w-[760px]">
      <div className="msg-bot-bubble px-4 py-3">
        {!hasBody && !m.error && <span className="scr-typing"><i /><i /><i /></span>}
        {m.intro && <div className="text-[13px] leading-[1.6] mb-1.5" style={{ color: 'var(--text)' }}><ReactMarkdown remarkPlugins={[remarkGfm]} components={md}>{m.intro}</ReactMarkdown></div>}
        {m.items.length > 0 && <Items items={m.items} />}
        {m.text && (
          <div className="text-[13px] ds-narration" style={{ color: 'var(--text)' }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={md}>{m.text}</ReactMarkdown>
          </div>
        )}
        {!m.text && m.items.length > 0 && !m.done && (
          <div className="flex items-center gap-2 mt-2 text-[11px]" style={{ color: 'var(--text-dim)' }}>
            {m.items.some((it) => it.kind === 'step' && it.status === 'call') ? <><span className="ds-spin sm" /> Working on SAS Viya…</> : <><span className="scr-typing"><i /><i /><i /></span> Writing it up…</>}
          </div>
        )}
        {m.error && <div className="text-[12px] mt-1" style={{ color: 'var(--red)' }}>{m.error}</div>}
      </div>
      {isLast && m.done && !busy && m.next?.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-2">
          {m.next.map((c) => (
            <button key={c.label} className={`suggestion-chip ${c.kind === 'next' ? 'primary' : ''}`} onClick={() => onChip(c.text)}>
              {c.kind === 'next' && <span className="chip-tag">NEXT</span>}{c.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* Steps and blocks in the order they happened: consecutive steps share one trace list. */
function Items({ items }) {
  const groups = [];
  for (const it of items) {
    const g = groups[groups.length - 1];
    if (it.kind === 'step' && g?.kind === 'steps') g.steps.push(it);
    else if (it.kind === 'step') groups.push({ kind: 'steps', steps: [it] });
    else groups.push(it);
  }
  return (
    <div className="space-y-2 my-1.5">
      {groups.map((g, i) => (g.kind === 'steps' ? <Steps key={i} steps={g.steps} /> : <Block key={i} block={g.block} />))}
    </div>
  );
}

function Steps({ steps }) {
  return (
    <div className="ds-steps">
      {steps.map((s) => <Step key={s.id} s={s} />)}
    </div>
  );
}

function Step({ s }) {
  const [logOpen, setLogOpen] = useState(false);
  const running = s.status === 'call';
  return (
    <div className={`ds-step ${running ? 'running' : 'done'}`}>
      <span className="ds-step-ic">{running ? <span className="ds-spin sm" /> : '✓'}</span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="ds-tool">{s.tool}</span>
          {s.args && <span className="ds-args">{s.args}</span>}
          {!running && s.ms != null && <span className="ds-ms">{s.ms >= 1000 ? `${(s.ms / 1000).toFixed(1)} s` : `${s.ms} ms`}</span>}
        </div>
        {running && s.progress && (
          <div className="ds-progress">
            <div className="ds-progress-bar"><i style={{ width: `${s.progress.pct}%` }} /></div>
            <span>{s.progress.label}</span>
          </div>
        )}
        {!running && s.result && <div className="ds-result">{s.result}</div>}
        {!running && s.log?.length > 0 && (
          <button className="ds-loglink" onClick={() => setLogOpen(!logOpen)}>{logOpen ? 'Hide the SAS log' : 'SAS log'}</button>
        )}
        {logOpen && <pre className="ds-log">{s.log.join('\n')}</pre>}
      </div>
    </div>
  );
}

function Block({ block: b }) {
  switch (b.kind) {
    case 'sas_code': return <SasCode b={b} />;
    case 'table': return <TableBlock b={b} />;
    case 'profile': return <ProfileBlock b={b} />;
    case 'leaderboard': return <Leaderboard b={b} />;
    case 'predictors': return <Predictors b={b} />;
    case 'scores': return <Scores b={b} />;
    case 'rules': return <Rules b={b} />;
    case 'flow': return <Flow b={b} />;
    case 'decisions': return <Decisions b={b} />;
    case 'handover': return <Handover b={b} />;
    case 'pointer': return <Pointer b={b} />;
    default: return null;
  }
}

function Card({ title, children, right, className = '' }) {
  return (
    <div className={`ds-card ${className}`}>
      {(title || right) && (
        <div className="ds-card-head">
          <span>{title}</span>
          {right}
        </div>
      )}
      <div className="ds-card-body">{children}</div>
    </div>
  );
}

function SasCode({ b }) {
  const [open, setOpen] = useState(true);
  return (
    <Card title={b.title} right={<button className="ds-loglink" onClick={() => setOpen(!open)}>{open ? 'Hide code' : 'Show code'}</button>}>
      {open && <pre className="ds-code">{b.code}</pre>}
    </Card>
  );
}

function TableBlock({ b }) {
  return (
    <Card title={b.title} right={<span className="ds-faint">{b.rows.length} of {fmtInt(b.total)} rows · {b.columns.length} columns</span>}>
      <div className="ds-scroll">
        <table className="ds-table">
          <thead><tr>{b.columns.map((c) => <th key={c.name}>{c.name}<em>{c.type}</em></th>)}</tr></thead>
          <tbody>{b.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j} className={typeof v === 'number' ? 'num' : ''}>{v}</td>)}</tr>)}</tbody>
        </table>
      </div>
      <div className="ds-cols">
        {b.columns.map((c) => (
          <div key={c.name} className={`ds-col ${c.name === 'deterioration_next_12m' ? 'target' : ''}`}>
            <span className="ds-col-name">{c.name}</span><span className="ds-col-about">{c.about}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function ProfileBlock({ b }) {
  const max = Math.max(...b.by_emirate.map((e) => e.n));
  return (
    <Card title="query_data · profile">
      <div className="ds-kpis">
        <Kpi v={fmtInt(b.rows)} l="patients" />
        <Kpi v={fmtPct(b.event_rate)} l="deteriorated in 12 months" />
        <Kpi v={`${b.mean_hba1c.toFixed(2)}%`} l="mean HbA1c" />
        <Kpi v={fmtPct(b.pct_hba1c_over_9)} l="HbA1c at or above 9" />
        <Kpi v={fmtPct(b.pct_low_adherence, 0)} l="adherence below 80%" />
        <Kpi v={b.mean_age.toFixed(0)} l="mean age" />
      </div>
      <div className="ds-bars">
        {b.by_emirate.map((e) => (
          <div key={e.emirate} className="ds-bar-row">
            <span className="ds-bar-label">{e.emirate}</span>
            <span className="ds-bar"><i style={{ width: `${(100 * e.n) / max}%` }} /></span>
            <span className="ds-bar-val">{fmtInt(e.n)} <em>· {fmtPct(e.event_rate)}</em></span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function Kpi({ v, l }) {
  return <div className="ds-kpi"><b>{v}</b><span>{l}</span></div>;
}

function Leaderboard({ b }) {
  return (
    <Card title={b.title} right={<span className="ds-faint">target {b.target} · {fmtInt(b.holdout)} holdout patients</span>}>
      <table className="ds-table plain">
        <thead><tr><th>Pipeline · algorithm</th><th className="num">AUC</th><th className="num">KS</th><th className="num">Misclassification</th><th /></tr></thead>
        <tbody>
          {b.rows.map((r) => (
            <tr key={r.algorithm} className={r.champion ? 'champion' : ''}>
              <td>{r.algorithm}</td><td className="num">{r.auc.toFixed(3)}</td><td className="num">{r.ks.toFixed(3)}</td><td className="num">{fmtPct(r.misclassification)}</td>
              <td>{r.champion && <span className="ds-champ">★ champion</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function Predictors({ b }) {
  return (
    <Card title={b.title}>
      <div className="ds-bars">
        {b.rows.map((p) => (
          <div key={p.feature} className="ds-bar-row">
            <span className="ds-bar-label">{p.label}</span>
            <span className="ds-bar"><i className={p.direction > 0 ? 'up' : 'down'} style={{ width: `${p.importance}%` }} /></span>
            <span className="ds-bar-val">{p.importance} <em>{p.direction > 0 ? '↑ raises risk' : '↓ lowers risk'}</em></span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function Scores({ b }) {
  return (
    <Card title={b.title}>
      <div className="ds-two">
        {b.rows.map((p) => (
          <div key={p.label} className="ds-patient">
            <div className="ds-patient-name">{p.label}</div>
            <div className="ds-patient-facts">{p.facts.join(' · ')}</div>
            <div className="ds-risk"><i style={{ width: `${Math.max(2, 100 * p.risk)}%`, background: p.risk >= 0.3 ? 'var(--red)' : p.risk >= 0.15 ? 'var(--amber)' : 'var(--green)' }} /></div>
            <div className="ds-risk-val"><b>{fmtPct(p.risk)}</b> risk of deterioration in the next 12 months</div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function Rules({ b }) {
  return (
    <Card title={b.title}>
      <div className="ds-sig">
        <span className="ds-sig-l">inputs</span>{b.signature.filter((s) => s.direction === 'input').map((s) => <span key={s.name} className="ds-term">{s.name} <em>{s.type}</em></span>)}
        <span className="ds-sig-l">outputs</span>{b.signature.filter((s) => s.direction === 'output').map((s) => <span key={s.name} className="ds-term out">{s.name} <em>{s.type}</em></span>)}
      </div>
      <table className="ds-table plain">
        <thead><tr><th>Rule</th><th>When</th><th>Priority</th><th>Channel</th></tr></thead>
        <tbody>
          {b.rows.map((r) => (
            <tr key={r.name}>
              <td><span className="ds-tool">{r.name}</span></td>
              <td><span className="ds-when">{r.kind}</span> {r.when}</td>
              <td><span className={`ds-prio ${PRIORITY_TONE[r.priority]}`}>{r.priority}</span></td>
              <td>{r.channel}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function Flow({ b }) {
  return (
    <Card title={`create_decision_flow · ${b.title}`}>
      <div className="ds-flow">
        <div className="ds-flow-col">
          <div className="ds-flow-l">Inputs</div>
          {b.inputs.map((n) => <div key={n} className="ds-flow-term">{n}</div>)}
        </div>
        <div className="ds-flow-arrow">→</div>
        <div className="ds-flow-step">
          <div className="ds-flow-l">Rule set step</div>
          <div className="ds-flow-name">{b.step}</div>
          <div className="ds-flow-note">{b.model}</div>
        </div>
        <div className="ds-flow-arrow">→</div>
        <div className="ds-flow-col">
          <div className="ds-flow-l">Outputs</div>
          {b.outputs.map((n) => <div key={n} className="ds-flow-term out">{n}</div>)}
        </div>
      </div>
    </Card>
  );
}

function Decisions({ b }) {
  return (
    <Card title={b.title}>
      <div className="ds-two">
        {b.rows.map((p) => (
          <div key={p.label} className="ds-patient">
            <div className="flex items-center justify-between gap-2">
              <div className="ds-patient-name">{p.label}</div>
              <span className={`ds-prio ${PRIORITY_TONE[p.priority]}`}>{p.priority}</span>
            </div>
            <div className="ds-patient-facts">risk {fmtPct(p.risk)} · matched <span className="ds-tool">{p.rule}</span></div>
            <div className="ds-decision-ch">{p.channel}</div>
            <div className="ds-patient-facts">{p.reason}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function Handover({ b }) {
  const [copied, setCopied] = useState(null);
  const copy = (k, v) => { navigator.clipboard?.writeText(v).then(() => { setCopied(k); setTimeout(() => setCopied(null), 1400); }).catch(() => {}); };
  return (
    <Card title={b.title}>
      <div className="ds-sub">Tool source · Bootcamp MCP · environment variables</div>
      {b.env.map((e) => (
        <div key={e.name} className="ds-env">
          <code>{e.name}={e.value}</code>
          <button className="ds-loglink" onClick={() => copy(e.name, `${e.name}=${e.value}`)}>{copied === e.name ? 'Copied' : 'Copy'}</button>
        </div>
      ))}
      <div className="ds-sub mt-2">Tools</div>
      <div className="flex flex-wrap gap-1">{b.tools.map((t) => <span key={t} className="ds-tool">{t}</span>)}</div>
      <div className="ds-sub mt-2">System prompt <button className="ds-loglink" onClick={() => copy('prompt', b.prompt)}>{copied === 'prompt' ? 'Copied' : 'Copy'}</button></div>
      <blockquote className="ds-quote">{b.prompt}</blockquote>
      <div className="ds-sub mt-2">Test questions · expected answers</div>
      <table className="ds-table plain">
        <tbody>{b.tests.map((t) => <tr key={t.q}><td>{t.q}</td><td className="num" style={{ whiteSpace: 'nowrap' }}><b>{t.a}</b></td></tr>)}</tbody>
      </table>
    </Card>
  );
}

function Pointer({ b }) {
  return (
    <div className="ds-pointer">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><path d="M12 8v4l2.5 2.5" /></svg>
      <div className="min-w-0 flex-1">
        <div className="ds-pointer-l">Where to look in SAS Viya</div>
        <div className="ds-pointer-path">{b.path}</div>
        <div className="ds-pointer-note">{b.note}</div>
      </div>
      {b.url && <a className="ds-open" href={b.url} target="_blank" rel="noreferrer">Open Viya ↗</a>}
    </div>
  );
}
