import { useEffect, useRef, useState } from 'react';
import { useApp } from '../context/AppContext';
import { getDashboard, getDataTables, getLinks, getStoryHero } from '../services/api';
import { AgentChip } from '../components/ui';

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
  { id: 'cohort_agent', name: 'Cohort', sub: 'REGISTRY QUERIES', color: '#8a6a4e' },
  { id: 'guideline_agent', name: 'Guidelines', sub: 'RAG · CITATIONS', color: '#3a8e5a' },
  { id: 'risk_agent', name: 'Risk · ML', sub: 'SCORE · SIMULATE', color: '#b06024' },
  { id: 'pophealth_agent', name: 'Pop-health', sub: 'MCP SERVER ★', color: '#b8862e', mcp: true },
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

function RiskRing({ pct }) {
  const r = 34, c = 2 * Math.PI * r;
  return (
    <svg viewBox="0 0 90 90" style={{ width: 96, height: 96 }}>
      <circle cx="45" cy="45" r={r} fill="none" stroke="rgba(15,23,42,0.08)" strokeWidth="9" />
      <circle cx="45" cy="45" r={r} fill="none" stroke="url(#risk-grad)" strokeWidth="9" strokeLinecap="round"
        strokeDasharray={c} strokeDashoffset={c * (1 - pct)} transform="rotate(-90 45 45)"
        style={{ transition: 'stroke-dashoffset 1.4s cubic-bezier(0.34,1.1,0.64,1)' }} />
      <defs>
        <linearGradient id="risk-grad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#b8862e" /><stop offset="1" stopColor="#2B5378" />
        </linearGradient>
      </defs>
      <text x="45" y="52" className="risk-ring-val">{Math.round(pct * 100)}%</text>
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

/* ─── How to use this app during the bootcamp: one card per tab ─── */
const TOUR = [
  { tab: 'overview', n: '1', title: 'Dashboard', sub: 'Understand the population',
    text: 'The registry at a glance: control, complications, care gaps, demand and cost. This is the population your agent will reason about.' },
  { tab: 'data', n: '2', title: 'Data & Documents', sub: 'The raw material',
    text: 'The eight registry tables you will load into SAS Viya, and the NHA guideline PDFs you will index in a RAM collection. Browse both here.' },
  { tab: 'assistant', n: '3', title: 'Assistant', sub: 'Play with the finished idea',
    text: 'Basira is a working population-health agent: a supervisor, specialists, cited guidelines, model scoring and human approval. Ask it anything to see the target.' },
  { tab: 'ram', n: '4', title: 'SAS RAM', sub: 'Build yours',
    text: 'Sign in to your RAM environment at the top of the page, pick the agent you built, and test it here with the same questions. Every tool, LLM and retrieval call is shown.' },
];

export default function LandingPage({ go }) {
  const { personaInfo } = useApp();
  const [ov, setOv] = useState(null);
  const [tables, setTables] = useState(null);
  const [hero, setHero] = useState(null);
  const [links, setLinks] = useState(null);

  useEffect(() => {
    getDashboard('overview').then(setOv).catch(() => {});
    getDataTables().then((r) => setTables(r.tables)).catch(() => {});
    getStoryHero().then(setHero).catch(() => {});
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
  const p = hero?.patient;

  return (
    <div className="landing">
      <div className="landing-inner">

        {/* ── HERO ── */}
        <section className="hero">
          <img src="/ehs-mark.png" alt="" className="hero-g" />
          <div className="relative z-[1]">
            <div className="section-eyebrow reveal d1">Emirates Health Services × SAS · Agentic AI Bootcamp</div>
            <h1 className="hero-title reveal d2">
              Build a population-health agent<br />
              <span className="hero-grad">on SAS RAM, in two days.</span>
            </h1>
            <p className="hero-lede mt-5 reveal d3">
              This is your workbench for the bootcamp, not a slide deck. It holds the use case you will build: a
              synthetic EHS diabetes registry, the clinical guidelines that go into your RAM collection, a working
              population-health assistant to learn from, and a page that connects to your own SAS Retrieval Agent
              Manager environment so you can test the agent you build with the same questions.
            </p>
            <div className="flex items-center gap-3 mt-7 reveal d4">
              <button className="btn-primary" onClick={() => go('assistant')}>Open the assistant</button>
              <button className="btn-secondary" onClick={() => go('overview')}>Explore the data</button>
              <button className="btn-secondary" onClick={() => go('ram')}>Build on SAS RAM</button>
            </div>
            <p className="text-[11px] mt-5 reveal d5" style={{ color: 'var(--text-faint)' }}>
              SAS Retrieval Agent Manager · SAS Viya · Model Context Protocol · cited guidelines · human-in-the-loop
            </p>
          </div>

          <div className="relative z-[1] reveal d3">
            <div className="glass-card p-5">
              <div className="flex items-center justify-between mb-2">
                <span className="ecg-live">Live · the registry you will work with</span>
                <span className="text-[10px] font-bold" style={{ color: 'var(--text-faint)' }}>36 months · 8 tables · FHIR R4 export</span>
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
              <span className="badge badge-green">Synthetic data · no PHI</span>
            </div>
          </div>
        </section>

        {/* ── YOUR ENVIRONMENTS ── */}
        <section className="landing-section pt-2">
          <div className="section-eyebrow">Your environments</div>
          <h2 className="section-title">Three doors. Everything you need on the day is behind one of them.</h2>
          <p className="section-sub mt-2 mb-4">
            Each opens in a new tab. SAS Viya is where the data, models and decisions live. SAS RAM is where you
            create the collection, the agent and its tools. The materials hold the decks, the labs and this application.
          </p>
          <div className="env-grid">
            {(links || []).map((l) => <EnvCard key={l.id} link={l} />)}
          </div>
        </section>

        {/* ── HOW TO USE THIS APP ── */}
        <section className="landing-section">
          <div className="section-eyebrow">How to use this app during the bootcamp</div>
          <h2 className="section-title">Four tabs, in the order you will need them.</h2>
          <div className="tour-grid mt-4">
            {TOUR.map((t) => (
              <button key={t.tab} className="tour-card reveal" onClick={() => go(t.tab)}>
                <span className="tour-num">{t.n}</span>
                <div className="min-w-0">
                  <div className="tour-title">{t.title}</div>
                  <div className="tour-sub">{t.sub}</div>
                  <p className="tour-text">{t.text}</p>
                </div>
              </button>
            ))}
          </div>
        </section>

        {/* ── WHAT YOU WILL BUILD ── */}
        <section className="landing-section grid grid-cols-2 gap-10 items-center">
          <div>
            <div className="section-eyebrow">What you will build</div>
            <h2 className="section-title">One RAM agent, grounded in documents,<br />connected to data and models through MCP.</h2>
            <p className="section-sub mt-3">
              The assistant in this app is the finished version. It plans, then routes each question to specialists:
              one queries the registry, one retrieves and cites the guidelines, one runs the risk model, one works through
              a population-health MCP server, and one drafts actions into a queue a clinician must approve. In RAM you
              build the same thing in four steps.
            </p>
            <div className="mt-5 space-y-3">
              {[
                ['A collection', 'upload the NHA guideline PDFs from the Documents tab; RAM indexes them for retrieval with citations.'],
                ['An agent', 'write its instructions: the persona, the rules (numbers only from tools, cite before recommending), the escalation points.'],
                ['Its tools', 'connect the SAS Viya MCP server for data, code and published models, and the population-health MCP server for cohorts, care gaps and policy what-ifs.'],
                ['A test', 'ask it the evaluation questions in the SAS RAM tab and read the trace: which tools it called, what it retrieved, what it answered.'],
              ].map(([t, d], i) => (
                <div key={i} className="flex items-start gap-3">
                  <span className="step-num">{i + 1}</span>
                  <p className="text-[12.5px] leading-relaxed" style={{ color: 'var(--text-md)' }}>
                    <b style={{ color: 'var(--text)' }}>{t}</b>: {d}
                  </p>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-1.5 mt-5">
              {['basira_supervisor', ...AGENTS.map((a) => a.id)].map((a) => <AgentChip key={a} agent={a} />)}
            </div>
          </div>
          <div className="glass-card p-6">
            <Constellation />
            <p className="text-[10.5px] text-center mt-2" style={{ color: 'var(--text-faint)' }}>
              The population-health specialist reaches its server over the Model Context Protocol. In RAM, MCP servers register as tool sources on the agent.
            </p>
          </div>
        </section>

        {/* ── THE USE CASE ── */}
        <section className="landing-section pb-8">
          <div className="section-eyebrow">The use case, in one patient</div>
          <h2 className="section-title">{p ? p.full_name : 'A patient'}: flagged by the model, not by the registry tier.</h2>
          <div className="grid grid-cols-[1.2fr_1fr] gap-6 mt-5 items-stretch">
            <div className="glass-card p-5 flex gap-5 items-center">
              <div className="w-16 h-16 rounded-2xl shrink-0 flex items-center justify-center text-white text-[18px] font-extrabold"
                style={{ background: 'var(--brand-grad)', boxShadow: '0 8px 20px rgba(43,83,120,0.3)' }}>
                {p ? p.full_name.split(' ').map((w) => w[0]).join('').slice(0, 2) : 'n/a'}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[16px] font-extrabold" style={{ color: 'var(--text)' }}>
                  {p?.full_name ?? 'Loading…'} <span className="text-[12px] font-semibold" style={{ color: 'var(--text-dim)' }}>{p ? `· ${p.age}, ${p.nationality}, ${p.facility_name}` : ''}</span>
                </p>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {(hero?.conditions || []).slice(0, 6).map((c) => <span key={c.condition} className="chip-cond">{c.condition}</span>)}
                </div>
                <div className="grid grid-cols-4 gap-3 mt-3">
                  {[['HbA1c', p ? `${p.hba1c_latest}%` : 'n/a'], ['HbA1c 12 mo ago', p ? `${p.hba1c_12m_ago ?? 'n/a'}%` : 'n/a'],
                    ['BMI · eGFR', p ? `${p.bmi} · ${Math.round(p.egfr_latest)}` : 'n/a'], ['Registry tier', p ? p.registry_risk_tier : 'n/a']].map(([k, v]) => (
                    <div key={k}>
                      <p className="text-[9px] font-bold tracking-widest uppercase" style={{ color: 'var(--text-faint)' }}>{k}</p>
                      <p className="text-[14px] font-extrabold" style={{ color: 'var(--text)' }}>{v}</p>
                    </div>
                  ))}
                </div>
                <div className="flex flex-wrap gap-1.5 mt-3">
                  {(p?.open_care_gaps || '').split(';').filter(Boolean).map((g) => (
                    <span key={g} className="chip-gap">{g.replace(/_/g, ' ')}</span>
                  ))}
                </div>
              </div>
              <div className="text-center shrink-0">
                <RiskRing pct={hero?.risk?.event_probability_12m ?? 0} />
                <p className="text-[9px] font-bold tracking-widest uppercase" style={{ color: 'var(--text-faint)' }}>12-mo deterioration risk</p>
              </div>
            </div>
            <div className="glass-card p-5 flex flex-col justify-between">
              <div>
                <p className="text-[12.5px] leading-relaxed" style={{ color: 'var(--text-md)' }}>
                  {p ? (
                    <>HbA1c has risen from <b>{p.hba1c_12m_ago ?? 'n/a'}%</b> to <b>{p.hba1c_latest}%</b> in twelve months on <b>metformin alone</b>
                    {p.ckd || p.albuminuria ? <>, with early kidney involvement (eGFR {Math.round(p.egfr_latest)})</> : <>, with a BMI of {p.bmi}</>}.
                    The registry's rule-based tier lists {p.gender === 'female' ? 'her' : 'him'} as <b>{p.registry_risk_tier}</b>. The deterioration model puts the 12-month
                    risk at <b>{Math.round((hero?.risk?.event_probability_12m ?? 0) * 100)}%</b>, and the guideline recommends adding an SGLT2 inhibitor or
                    GLP-1 receptor agonist at this point. This is the kind of answer your agent should give: the number from the data, the recommendation
                    from the cited guideline, and a draft that waits for a clinician.</>
                  ) : 'Loading the case…'}
                </p>
              </div>
              <button className="btn-primary mt-4 self-start" onClick={() => go('assistant')}>See the assistant answer it</button>
            </div>
          </div>
          <p className="text-[10.5px] mt-6" style={{ color: 'var(--text-faint)' }}>
            Signed in as {personaInfo.name}. Switch persona at the top right. All patient data is synthetic and not for clinical use.
          </p>
        </section>
      </div>
    </div>
  );
}
