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

const FALLBACK_LINKS = [
  { id: 'ram', label: 'SAS RAM', sub: 'Where the agent is built and run', url: '' },
  { id: 'viya', label: 'SAS Viya', sub: 'Data, models and dashboards', url: '' },
];
// RAM is where the agent lives, so it comes first and biggest.
const LINK_ORDER = ['ram', 'viya'];
const linkStyle = (id) => (id === 'ram' ? 'btn-primary btn-xl' : id === 'viya' ? 'btn-secondary btn-lg' : 'btn-secondary');

/* One of the environment doors. Opens in a new tab; greyed out until its URL is set. The
   sign-in details for Viya and RAM are deliberately not on the page: they go on a slide. */
function Door({ link }) {
  const cls = linkStyle(link.id);
  const body = (
    <span className="btn-text">
      {link.label}
      {link.sub && <span className="btn-sub">{link.sub}</span>}
    </span>
  );
  const button = !link.url ? (
    <span className={`${cls} btn-disabled`} title="Link will be shared on the day">{body}</span>
  ) : (
    <a className={cls} href={link.url} target="_blank" rel="noopener noreferrer" title={link.url}>
      {body}
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M7 17L17 7M9 7h8v8" />
      </svg>
    </a>
  );
  return <div className={`door ${link.id}`}>{button}</div>;
}

export default function LandingPage() {
  const [ov, setOv] = useState(null);
  const [tables, setTables] = useState(null);
  const [links, setLinks] = useState(FALLBACK_LINKS);

  useEffect(() => {
    getDashboard('overview').then(setOv).catch(() => {});
    getDataTables().then((r) => setTables(r.tables)).catch(() => {});
  }, []);
  useEffect(() => {
    getLinks().then((r) => { if (r?.links?.length) setLinks(r.links.filter((l) => l.id !== 'materials')); }).catch(() => {});
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
        <section className="hero">
          <img src="/sas-logo.png" alt="" className="hero-g" />
          <div className="relative z-[1]">
            <div className="section-eyebrow reveal d1">SAS · Composite AI</div>
            <h1 className="hero-title reveal d2">
              Composite AI, in <span className="hero-grad">health care.</span>
            </h1>
            <p className="hero-lede mt-5 reveal d3">
              Predictive models, deterministic rules and generative agents, working as one, under human oversight.{' '}
              <b>Population health</b> is a diabetes registry, its models, guidelines and a finished agent.{' '}
              <b>Cancer screening</b> is a screening programme: the rules, the model and an agent that
              drafts, is checked, and waits for approval. <b>SAS RAM</b> is where such an agent is built and run.
            </p>
            <div className="doors reveal d4">
              {[...links].sort((a, b) => LINK_ORDER.indexOf(a.id) - LINK_ORDER.indexOf(b.id))
                .map((l) => <Door key={l.id} link={l} />)}
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
      </div>
    </div>
  );
}
