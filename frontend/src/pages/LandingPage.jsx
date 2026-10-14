import { useEffect, useRef, useState } from 'react';
import { getCrcDashboard, getDashboard, getLinks } from '../services/api';

/* Home: the composite-AI story. A hero that says what composite AI is here, a strip showing how
   one decision travels through the layers, the two stories with live numbers and their chapters,
   and the two environment doors. Everything clickable goes somewhere in the app. */

/* ─── count-up hook (ease-out) ─── */
function useCountUp(target, duration = 1700, start = true) {
  const [v, setV] = useState(0);
  const raf = useRef(null);
  useEffect(() => {
    if (!start || target == null) return;
    const t0 = performance.now();
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / duration);
      const e = 1 - Math.pow(1 - p, 3);
      setV(target * e);
      if (p < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [target, duration, start]);
  return v;
}

function Counter({ value, format = (v) => Math.round(v).toLocaleString(), label }) {
  const v = useCountUp(value);
  return (
    <div>
      <div className="counter-val">{value == null ? '…' : format(v)}</div>
      <div className="counter-lbl">{label}</div>
    </div>
  );
}

/* ─── The composite: four kinds of intelligence around one agent, a person at the end ─── */
const NODES = [
  { id: 'rules', label: 'Rules', sub: 'DETERMINISTIC', x: 92, y: 84, color: '#1B3650', verb: 'validates', tab: 'crc_rules' },
  { id: 'model', label: 'Model', sub: 'PREDICTIVE', x: 428, y: 84, color: '#b8862e', verb: 'prioritises', tab: 'crc_model' },
  { id: 'retrieval', label: 'Retrieval', sub: 'GROUNDED', x: 92, y: 266, color: '#3a8e5a', verb: 'cites', tab: 'crc_documents' },
  { id: 'human', label: 'Human', sub: 'APPROVES', x: 428, y: 266, color: '#b03c3c', verb: 'decides', tab: 'crc_agent' },
];
function Composite({ onNavigate }) {
  const cx = 260, cy = 175;
  const halo = { paintOrder: 'stroke', stroke: 'rgba(255,254,251,0.92)', strokeWidth: 4, strokeLinejoin: 'round' };
  return (
    <svg viewBox="0 0 520 350" className="composite-svg" role="img" aria-label="Rules, model, retrieval and a human around one agent">
      <defs>
        <linearGradient id="core-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#4A78A0" /><stop offset="1" stopColor="#1B3650" />
        </linearGradient>
      </defs>
      <circle cx={cx} cy={cy} r={152} fill="none" stroke="rgba(43,83,120,0.09)" strokeWidth="1" />
      <circle className="cst-ring" cx={cx} cy={cy} r={116} />
      {NODES.map((n) => <line key={n.id} className={`cst-link ${n.id === 'human' ? 'gold' : ''}`} x1={n.x} y1={n.y} x2={cx} y2={cy} />)}
      {NODES.map((n) => {
        const mx = (n.x + cx) / 2, my = (n.y + cy) / 2;
        return <text key={`v-${n.id}`} x={mx} y={my + (n.y < cy ? -7 : 14)} fontSize="9" fontWeight="700" fill="#64748b" textAnchor="middle" letterSpacing="0.08em" style={halo}>{n.verb.toUpperCase()}</text>;
      })}
      <g className="cst-node" onClick={() => onNavigate?.('crc_agent')} style={{ cursor: 'pointer' }}>
        <circle className="cst-core" cx={cx} cy={cy} r={52} />
        <text className="cst-core-text" x={cx} y={cy - 3}>Agent</text>
        <text className="cst-core-sub" x={cx} y={cy + 12}>REASONS · DRAFTS</text>
      </g>
      {NODES.map((n) => (
        <g key={n.id} className="cst-node" onClick={() => onNavigate?.(n.tab)} style={{ cursor: 'pointer' }}>
          <circle className="body" cx={n.x} cy={n.y} r={37} stroke={n.color} />
          <text className="lbl" x={n.x} y={n.y - 1}>{n.label}</text>
          <text className="sub" x={n.x} y={n.y + 12}>{n.sub}</text>
        </g>
      ))}
    </svg>
  );
}

const FLOW = [
  { step: '01 · Predict', title: 'A model scores the risk', text: 'Deterioration risk in the registry; the chance an invitation goes unanswered in the screening programme. Trained, versioned, explained per person.', tab: 'crc_model' },
  { step: '02 · Validate', title: 'The rules say what is allowed', text: 'Eligibility, the test, the interval, the urgent route. Thirteen rules the agent cannot overrule, each citing its policy section.', tab: 'crc_rules' },
  { step: '03 · Reason', title: 'The agent plans and retrieves', text: 'A function-calling supervisor works the tools in order and cites the policy page it relied on. Numbers come from tools, never from memory.', tab: 'crc_agent' },
  { step: '04 · Act', title: 'A draft, never an action', text: 'The message or referral is written, checked by a deterministic validator, and queued. Nothing reaches a patient or a system.', tab: 'crc_agent' },
  { step: '05 · Approve', title: 'A person decides', text: 'Approve or reject in the queue. Every score, rule outcome, draft and decision is on the audit trail.', tab: 'crc_agent' },
];

const STORIES = [
  {
    id: 'pop', eyebrow: 'Story 1 · Population health', title: 'A diabetes registry, and an agent that works its panel',
    text: '4,000 people living with diabetes across 18 facilities. Dashboards you can filter, a deterioration model you can interrogate, guidelines the agent cites by page, and Basira: a supervisor and five specialist agents that review a panel, draft a prescription and wait for a clinician.',
    cta: 'Open population health', home: 'overview',
    chapters: [['overview', 'Registry'], ['geography', 'Geography'], ['simulator', 'Simulator'], ['data', 'Data'], ['documents', 'Documents'], ['assistant', 'Agent']],
  },
  {
    id: 'crc', eyebrow: 'Story 2 · Cancer screening', title: 'A screening programme where every layer knows its place',
    text: '12,000 residents of screening age. The rules say who is due and which test; the model says who will not act on the invitation; the agent writes the message, a validator checks it, and the navigator approves it. Symptoms override everything, and no model is asked.',
    cta: 'Open cancer screening', home: 'crc_programme',
    chapters: [['crc_programme', 'Programme'], ['crc_rules', 'Rules'], ['crc_model', 'Model'], ['screening', 'Screening check'], ['crc_data', 'Data'], ['crc_documents', 'Documents'], ['crc_agent', 'Agent']],
  },
];

const FALLBACK_LINKS = [
  { id: 'ram', label: 'SAS RAM', sub: 'Where the agent is built and run', url: '' },
  { id: 'viya', label: 'SAS Viya', sub: 'Data, models and dashboards', url: '' },
];

function Door({ link }) {
  const inner = (
    <>
      <span className="dot" style={{ background: link.url ? 'var(--green)' : 'var(--text-faint)' }} />
      <b>{link.label}</b><span style={{ color: 'var(--text-dim)', fontWeight: 600 }}>{link.sub}</span>
      {link.url && <span aria-hidden="true">↗</span>}
    </>
  );
  if (!link.url) return <span className="gcloud-chip off" title="Link not configured yet">{inner}</span>;
  return <a className="gcloud-chip" href={link.url} target="_blank" rel="noopener noreferrer" title={link.url}>{inner}</a>;
}

export default function LandingPage({ onNavigate }) {
  const go = (id) => onNavigate?.(id);
  const [ov, setOv] = useState(null);
  const [crc, setCrc] = useState(null);
  const [links, setLinks] = useState(FALLBACK_LINKS);
  useEffect(() => {
    getDashboard('overview').then(setOv).catch(() => {});
    getCrcDashboard().then(setCrc).catch(() => {});
    getLinks().then((r) => { if (r?.links?.length) setLinks(r.links.filter((l) => l.id !== 'materials')); }).catch(() => {});
  }, []);
  const num = (s) => (s == null ? null : parseFloat(String(s).replace(/,/g, '')));
  const kpi = ov?.kpis || []; const ck = crc?.kpis || [];
  const pop = { patients: num(kpi[0]?.value), controlled: num(kpi[2]?.value), overdue: num(kpi[4]?.value), gaps: ov?.care_gaps?.reduce((s, g) => s + (g.patients || 0), 0) ?? null };
  const scr = { eligible: num(ck[0]?.value), upToDate: num(ck[1]?.value), due: num(ck[2]?.value), fitPos: crc?.fit_positive_no_colonoscopy ?? null };
  const pct = (v) => `${v.toFixed(1)}%`;

  return (
    <div className="landing">
      <div className="landing-inner">
        <section className="hero">
          <img src="/sas-logo.png" alt="" className="hero-g" />
          <div className="relative z-[1]">
            <div className="section-eyebrow reveal d1">SAS · Composite AI</div>
            <h1 className="hero-title reveal d2">
              Composite AI, in <span className="hero-grad">health care.</span>
            </h1>
            <p className="hero-lede mt-5 reveal d3">
              One workflow, four kinds of intelligence. A <b>predictive model</b> says who is at risk. <b>Deterministic rules</b> say
              what the policy allows. A <b>generative agent</b> reasons, retrieves the evidence and drafts the action. A <b>person</b> approves it.
              Two live stories show every seam.
            </p>
            <div className="hero-ctas reveal d4">
              <button type="button" className="btn-primary btn-lg" onClick={() => go('overview')}>
                <span className="btn-text">Population health<span className="btn-sub">A registry and its agent</span></span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
              </button>
              <button type="button" className="btn-secondary btn-lg" onClick={() => go('crc_programme')}>
                <span className="btn-text">Cancer screening<span className="btn-sub">Rules, model, agent, approval</span></span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
              </button>
            </div>
            <div className="env-links reveal d5">
              <span className="env-links-lbl">Environment</span>
              {links.map((l) => <Door key={l.id} link={l} />)}
            </div>
          </div>

          <div className="relative z-[1] reveal d3">
            <div className="glass-card composite-card">
              <div className="flex items-center justify-between mb-1">
                <span className="ecg-live">Live · one decision, four layers</span>
                <span className="text-[10px] font-bold" style={{ color: 'var(--text-faint)' }}>click a node</span>
              </div>
              <Composite onNavigate={go} />
              <div className="grid grid-cols-4 gap-3 pt-4 border-t border-[rgba(15,23,42,0.07)]">
                <Counter value={pop.patients} label="In the registry" />
                <Counter value={scr.eligible} label="Eligible for screening" />
                <Counter value={13} label="Policy rules" />
                <Counter value={5} label="Trained models" />
              </div>
            </div>
          </div>
        </section>

        <section className="landing-section">
          <div className="section-eyebrow">How a decision is made here</div>
          <h2 className="section-title">Predict, validate, reason, act, approve.</h2>
          <p className="section-sub mt-2">The language model never computes a number, decides eligibility or sends anything. Each layer is shown doing its own job, and the hand-offs are visible in every trace.</p>
          <div className="flow-grid mt-6">
            {FLOW.map((f, i) => (
              <button type="button" key={f.step} className={`flow-card reveal d${Math.min(i + 1, 5)}`} onClick={() => go(f.tab)}>
                <span className="flow-step">{f.step}</span>
                <span className="flow-title">{f.title}</span>
                <span className="flow-text">{f.text}</span>
                <span className="flow-go">Open →</span>
              </button>
            ))}
          </div>
        </section>

        <section className="landing-section">
          <div className="section-eyebrow">Two stories, one method</div>
          <h2 className="section-title">Follow either from the data to the approved action.</h2>
          <div className="story-grid mt-6">
            {STORIES.map((s) => (
              <article key={s.id} className="glass-card story-card">
                <div>
                  <div className="section-eyebrow" style={{ marginBottom: 6 }}>{s.eyebrow}</div>
                  <h3>{s.title}</h3>
                  <p className="mt-2">{s.text}</p>
                </div>
                <div className="story-kpis">
                  {s.id === 'pop' ? (
                    <>
                      <Counter value={pop.patients} label="Patients" />
                      <Counter value={pop.controlled} format={pct} label="Well controlled" />
                      <Counter value={pop.overdue} label="HbA1c overdue" />
                      <Counter value={pop.gaps} label="Open care gaps" />
                    </>
                  ) : (
                    <>
                      <Counter value={scr.eligible} label="Eligible 40 to 75" />
                      <Counter value={scr.upToDate} format={pct} label="Up to date" />
                      <Counter value={scr.due} label="Due or overdue" />
                      <Counter value={scr.fitPos} label="FIT+ no colonoscopy" />
                    </>
                  )}
                </div>
                <div className="chapters">
                  {s.chapters.map(([id, label], i) => (
                    <button type="button" key={id} className="chapter" onClick={() => go(id)}><i>{i + 1}</i>{label}</button>
                  ))}
                </div>
                <div className="story-foot">
                  <span className="text-[10.5px]" style={{ color: 'var(--text-faint)' }}>{s.chapters.length} chapters · the agent comes last</span>
                  <button type="button" className="btn-primary" onClick={() => go(s.home)}>{s.cta}</button>
                </div>
              </article>
            ))}
          </div>
        </section>

        <div className="landing-foot">
          Synthetic data throughout · an educational prototype, not for clinical use · built on SAS Viya and SAS Retrieval Agent Manager
        </div>
      </div>
    </div>
  );
}
