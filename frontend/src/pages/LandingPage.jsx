import { useEffect, useRef, useState } from 'react';
import { getDashboard, getDataTables, getLinks } from '../services/api';

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

function Counter({ value, format, label }) {
  const v = useCountUp(value);
  return (
    <div>
      <div className="counter-val">{value == null ? 'n/a' : format(v)}</div>
      <div className="counter-lbl">{label}</div>
    </div>
  );
}

/* ─── The ECG: a synthetic normal-sinus trace, drawn on loop ─── */
const ECG_D = (() => {
  const beat = (x) => `L${x} 80 L${x + 14} 80 L${x + 20} 70 L${x + 26} 80 L${x + 40} 80 L${x + 46} 84 L${x + 50} 22 L${x + 55} 108 L${x + 60} 80 L${x + 78} 80 L${x + 90} 66 L${x + 102} 80`;
  return `M0 80 ${beat(20)} ${beat(170)} ${beat(320)} ${beat(470)} L640 80`;
})();

const AGENTS = [
  { id: 'cohort_agent', name: 'Data', sub: 'SAS VIYA · MCP', color: '#8a6a4e' },
  { id: 'guideline_agent', name: 'Guidelines', sub: 'RAM COLLECTION', color: '#3a8e5a' },
  { id: 'risk_agent', name: 'Models', sub: 'SCORE · SIMULATE', color: '#b06024' },
  { id: 'pophealth_agent', name: 'Pop-health', sub: 'MCP SERVER', color: '#b8862e', mcp: true },
  { id: 'action_agent', name: 'Actions', sub: 'HUMAN-IN-LOOP', color: '#2B5378' },
];

function Constellation() {
  const cx = 260, cy = 176, R = 128;
  const nodes = AGENTS.map((a, i) => {
    const ang = (-90 + i * 72) * (Math.PI / 180);
    return { ...a, x: cx + R * Math.cos(ang), y: cy + R * Math.sin(ang) };
  });
  return (
    <svg viewBox="0 0 520 352" style={{ width: '100%', height: 'auto', overflow: 'visible' }}>
      <defs>
        <linearGradient id="core-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#4A78A0" /><stop offset="1" stopColor="#1B3650" />
        </linearGradient>
      </defs>
      {nodes.map((n) => (
        <line key={`l-${n.id}`} x1={cx} y1={cy} x2={n.x} y2={n.y} className={`cst-link ${n.mcp ? 'gold' : ''}`} />
      ))}
      <g className="cst-node">
        <circle cx={cx} cy={cy} r="50" className="cst-core" />
        <text x={cx} y={cy - 4} className="cst-core-text">RAM agent</text>
        <text x={cx} y={cy + 11} className="cst-core-sub">LLM · TOOLS</text>
      </g>
      {nodes.map((n) => (
        <g key={n.id} className="cst-node">
          {n.mcp && <circle cx={n.x} cy={n.y} r="44" className="cst-ring" />}
          <circle cx={n.x} cy={n.y} r="36" className="body" stroke={n.color} />
          <text x={n.x} y={n.y - 1} className="lbl">{n.name}</text>
          <text x={n.x} y={n.y + 12} className="sub">{n.sub}</text>
        </g>
      ))}
    </svg>
  );
}

/* ─── The three bootcamp environments: SAS Viya, SAS RAM, the materials ─── */
const ENV_ICONS = {
  viya: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 17c3-8 6-8 9 0s6 8 9 0" /><path d="M3 7h18" opacity="0.55" />
    </svg>
  ),
  ram: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="7" r="3" /><circle cx="5" cy="17" r="3" /><circle cx="19" cy="17" r="3" />
      <path d="M12 10v3M7.5 15l2.5-2M16.5 15l-2.5-2" />
    </svg>
  ),
  materials: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
      <path d="M9 7h7M9 11h5" />
    </svg>
  ),
};

function EnvCard({ link }) {
  const ready = Boolean(link.url);
  const body = (
    <>
      <div className={`env-icon ${link.icon}`}>{ENV_ICONS[link.icon]}</div>
      <div className="min-w-0">
        <div className="env-label">{link.label}</div>
        <div className="env-sub">{ready ? link.sub : 'Link will be shared on the day'}</div>
      </div>
      <span className="env-cta">{ready ? 'Open ↗' : 'Soon'}</span>
    </>
  );
  if (!ready) return <div className="env-card disabled reveal">{body}</div>;
  return (
    <a className="env-card reveal" href={link.url} target="_blank" rel="noopener noreferrer" title={link.url}>
      {body}
    </a>
  );
}

/* ─── The tabs, in the order you will need them ─── */
const TOUR = [
  { tab: 'overview', n: '1', title: 'Dashboard', text: 'Understand the population.' },
  { tab: 'data', n: '2', title: 'Data & Documents', text: 'The tables for SAS Viya and the guideline PDFs for your RAM collection.' },
  { tab: 'assistant', n: '3', title: 'Assistant', text: 'A finished population-health agent. Ask it anything.' },
  { tab: 'ram', n: '4', title: 'SAS RAM', text: 'Sign in to your environment and test the agent you build.' },
];

const BUILD_STEPS = [
  ['A collection', 'the guideline PDFs, indexed for cited retrieval'],
  ['An agent', 'its instructions: persona, rules, escalation'],
  ['Its tools', 'the SAS Viya MCP server and the population-health MCP server'],
  ['A test', 'the evaluation questions, with the trace'],
];

export default function LandingPage({ go }) {
  const [ov, setOv] = useState(null);
  const [tables, setTables] = useState(null);
  const [links, setLinks] = useState(null);

  useEffect(() => {
    getDashboard('overview').then(setOv).catch(() => {});
    getDataTables().then((r) => setTables(r.tables)).catch(() => {});
    getLinks().then((r) => setLinks(r.links)).catch(() => setLinks([
      { id: 'viya', label: 'SAS Viya environment', sub: '', url: '', icon: 'viya' },
      { id: 'ram', label: 'SAS RAM environment', sub: '', url: '', icon: 'ram' },
      { id: 'materials', label: 'Bootcamp materials', sub: 'Decks, labs, data and this application', url: 'https://github.com/raedaldweik/Agentic-Bootcamp', icon: 'materials' },
    ]));
  }, []);

  const rows = (name) => tables?.find((t) => t.name === name)?.rows;
  const kpi = ov?.kpis || [];
  const patients = rows('patients');
  const obs = rows('observations');
  const enc = rows('encounters');
  const gaps = rows('care_gaps');
  const costM = ov ? parseFloat(kpi[5]?.value) : null;
  const overdue = ov ? kpi[4]?.value : null;

  return (
    <div className="landing">
      <div className="landing-inner">

        {/* ── HERO ── */}
        <section className="hero">
          <img src="/ehs-mark.png" alt="" className="hero-g" />
          <div className="relative z-[1]">
            <div className="section-eyebrow reveal d1">Emirates Health Services × SAS</div>
            <h1 className="hero-title reveal d2">
              Build a population-health<br />
              <span className="hero-grad">agent on SAS RAM.</span>
            </h1>
            <p className="hero-lede mt-5 reveal d3">
              Your workbench for the two days: the data, the guidelines, a finished agent to learn from,
              and a door into your own RAM environment to test what you build.
            </p>
            <div className="flex items-center gap-3 mt-7 reveal d4">
              <button className="btn-primary" onClick={() => go('assistant')}>Open the assistant</button>
              <button className="btn-secondary" onClick={() => go('ram')}>Build on SAS RAM</button>
            </div>
          </div>

          <div className="relative z-[1] reveal d3">
            <div className="glass-card p-5">
              <div className="flex items-center justify-between mb-2">
                <span className="ecg-live">Live · the registry</span>
                <span className="text-[10px] font-bold" style={{ color: 'var(--text-faint)' }}>36 months · 8 tables · synthetic</span>
              </div>
              <div className="ecg-wrap">
                <svg viewBox="0 0 640 160" style={{ width: '100%', height: '100%' }} preserveAspectRatio="none">
                  <defs>
                    <linearGradient id="ecg-grad" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0" stopColor="#2B5378" /><stop offset="0.6" stopColor="#b8862e" /><stop offset="1" stopColor="#d4a64f" />
                    </linearGradient>
                  </defs>
                  <path d={ECG_D} className="ecg-base" />
                  <path d={ECG_D} className="ecg-path" />
                </svg>
              </div>
              <div className="grid grid-cols-4 gap-3 mt-2 pt-4 border-t border-[rgba(15,23,42,0.07)]">
                <Counter value={patients} format={(v) => Math.round(v).toLocaleString()} label="Patients" />
                <Counter value={obs} format={(v) => `${(v / 1000).toFixed(0)}k`} label="Observations" />
                <Counter value={enc} format={(v) => `${(v / 1000).toFixed(0)}k`} label="Encounters" />
                <Counter value={costM} format={(v) => `${v.toFixed(1)}M`} label="AED / year" />
              </div>
            </div>
            <div className="flex items-center gap-2 mt-3 justify-end">
              <span className="badge badge-red">{overdue ?? 'n/a'} HbA1c tests overdue</span>
              <span className="badge badge-amber">{gaps?.toLocaleString() ?? 'n/a'} open care gaps</span>
            </div>
          </div>
        </section>

        {/* ── YOUR ENVIRONMENTS ── */}
        <section className="landing-section pt-2">
          <div className="section-eyebrow">Your environments</div>
          <h2 className="section-title">Three doors. Each opens in a new tab.</h2>
          <div className="env-grid mt-4">
            {(links || []).map((l) => <EnvCard key={l.id} link={l} />)}
          </div>
        </section>

        {/* ── THE TABS ── */}
        <section className="landing-section">
          <div className="section-eyebrow">This app</div>
          <h2 className="section-title">Four tabs, in the order you will need them.</h2>
          <div className="tour-grid mt-4">
            {TOUR.map((t) => (
              <button key={t.tab} className="tour-card reveal" onClick={() => go(t.tab)}>
                <span className="tour-num">{t.n}</span>
                <div className="min-w-0">
                  <div className="tour-title">{t.title}</div>
                  <p className="tour-text">{t.text}</p>
                </div>
              </button>
            ))}
          </div>
        </section>

        {/* ── WHAT YOU WILL BUILD ── */}
        <section className="landing-section pb-10 grid grid-cols-2 gap-10 items-center">
          <div>
            <div className="section-eyebrow">What you will build</div>
            <h2 className="section-title">One RAM agent, in four steps.</h2>
            <div className="mt-5 space-y-3">
              {BUILD_STEPS.map(([t, d], i) => (
                <div key={i} className="flex items-start gap-3">
                  <span className="step-num">{i + 1}</span>
                  <p className="text-[12.5px] leading-relaxed" style={{ color: 'var(--text-md)' }}>
                    <b style={{ color: 'var(--text)' }}>{t}</b>: {d}
                  </p>
                </div>
              ))}
            </div>
          </div>
          <div className="glass-card p-6">
            <Constellation />
          </div>
        </section>
      </div>
    </div>
  );
}
