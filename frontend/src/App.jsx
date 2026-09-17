import { useEffect, useState } from 'react';
import { AppProvider, PERSONAS, useApp } from './context/AppContext';
import { getHealth, getLinks } from './services/api';
import LandingPage from './pages/LandingPage';
import AssistantPage from './pages/AssistantPage';
import DashboardOverview from './pages/DashboardOverview';
import QueuePage from './pages/QueuePage';
import DocumentsPage from './pages/DocumentsPage';
import DataPage from './pages/DataPage';
import AuditPage from './pages/AuditPage';
import EvaluationPage from './pages/EvaluationPage';
import SimulatorPage from './pages/SimulatorPage';
import RamCopilotPage from './ram/RamCopilotPage';

function Bokeh() {
  return (
    <div className="bokeh-layer">
      <div className="bokeh-dot mega-blue a1" /><div className="bokeh-dot mega-cyan a2" />
      <div className="bokeh-dot mega-purple a3" /><div className="bokeh-dot mega-amber a4" />
      <div className="bokeh-dot mega-cyan a5" />
      <div className="bokeh-dot blue-blob m1" /><div className="bokeh-dot cyan-blob m2" />
      <div className="bokeh-dot blue-blob m3" /><div className="bokeh-dot cyan-blob m4" />
      <div className="bokeh-dot blue-blob m5" /><div className="bokeh-dot purple-blob m6" />
      <div className="bokeh-dot blue-blob m7" /><div className="bokeh-dot amber-blob m8" />
      <div className="bokeh-dot cyan-blob m9" /><div className="bokeh-dot blue-blob m10" />
    </div>
  );
}

/** Persona picker (light glass dropdown). */
function PersonaSelector() {
  const { persona, setPersona, personaInfo } = useApp();
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)}
        className="flex items-center gap-2 pl-3 pr-2.5 py-1.5 rounded-lg text-[12px] font-semibold transition-all"
        style={{
          background: 'rgba(255,255,255,0.65)', backdropFilter: 'blur(12px)',
          border: '1px solid rgba(43,83,120,0.22)', color: 'var(--text)', minWidth: 210,
        }}>
        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: 'var(--green)' }} />
        <span className="flex-1 text-left truncate">{personaInfo.name}</span>
        <span className="text-[8.5px] font-bold tracking-wider uppercase px-1.5 py-0.5 rounded shrink-0"
          style={{ background: 'rgba(43,83,120,0.10)', color: 'var(--brand)' }}>
          {persona}
        </span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" strokeWidth="2.5"
          style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-1 rounded-xl shadow-xl overflow-hidden z-50 w-[280px] animate-fade-up"
            style={{ background: 'rgba(255,255,255,0.97)', border: '1px solid rgba(43,83,120,0.2)', backdropFilter: 'blur(20px)' }}>
            <p className="px-3 pt-2.5 pb-1 text-[9px] font-bold tracking-widest uppercase" style={{ color: 'var(--text-dim)' }}>
              Personas
            </p>
            <div className="pb-1.5">
              {Object.values(PERSONAS).map((u) => {
                const active = u.id === persona;
                return (
                  <button key={u.id} onClick={() => { setPersona(u.id); setOpen(false); }}
                    className="w-full text-left px-3 py-2 transition-all hover:bg-[rgba(43,83,120,0.06)] flex items-center gap-2.5"
                    style={active ? { background: 'rgba(43,83,120,0.10)', borderLeft: '3px solid var(--brand)' }
                      : { borderLeft: '3px solid transparent' }}>
                    <div className={`w-7 h-7 rounded-full ${u.color} flex items-center justify-center text-white text-[10px] font-bold shrink-0`}>
                      {u.avatar}
                    </div>
                    <div className="min-w-0">
                      <p className="text-[12px] font-semibold truncate" style={{ color: active ? 'var(--brand-lo)' : 'var(--text)' }}>{u.name}</p>
                      <p className="text-[10.5px] truncate" style={{ color: 'var(--text-dim)' }}>{u.sub}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Header({ tab, setTab }) {
  const [health, setHealth] = useState(null);
  const [ehsLogo, setEhsLogo] = useState('/ehs-logo.png');
  useEffect(() => {
    let timer;
    const tick = () => getHealth().then((h) => {
      setHealth(h);
      // keep polling until the agent graph has warmed up (or the key has failed)
      if (h?.mode === 'multi-agent' && !h.warmup?.ready) timer = setTimeout(tick, 3000);
    }).catch(() => setHealth({ status: 'down' }));
    tick();
    // A hosted logo can be plugged in through EHS_LOGO_URL without a rebuild.
    getLinks().then((r) => { if (r?.branding?.ehs_logo_url) setEhsLogo(r.branding.ehs_logo_url); }).catch(() => {});
    return () => clearTimeout(timer);
  }, []);
  const ok = health?.status === 'ok';
  const selfTest = health?.warmup?.self_test;
  const warming = ok && health.mode === 'multi-agent' && !health.warmup?.ready;
  const keyBad = ok && health.mode === 'multi-agent' && selfTest && !selfTest.ok;

  const tabs = [
    { id: 'landing', label: 'Home' },
    { id: 'assistant', label: 'Assistant' },
    { id: 'overview', label: 'Dashboard' },
    { id: 'simulator', label: 'Simulator' },
    { id: 'ram', label: 'SAS RAM' },
    { id: 'evaluation', label: 'Evaluation' },
    { id: 'queue', label: 'Queue' },
    { id: 'documents', label: 'Documents' },
    { id: 'data', label: 'Data' },
    { id: 'audit', label: 'Audit' },
  ];

  return (
    <header className="app-header">
      <button onClick={() => setTab('landing')} title="Home">
        <img className="brand-logo" src={ehsLogo} alt="Emirates Health Services"
          onError={(e) => { if (e.target.src.indexOf('/ehs-logo.png') === -1) e.target.src = '/ehs-logo.png'; }} />
      </button>

      <div className="title-block">
        <div className="header-eyebrow">Emirates Health Services · Agentic AI Bootcamp</div>
        <div className="title-row">
          <h1 className="app-title">
            <b>Basira</b> <span className="title-ar">بصيرة</span> <span className="title-sep">·</span> Population Health Intelligence
          </h1>
          <div className="accent-line" />
        </div>
        <div className="nav-row">
          <div className="seg-track">
            {tabs.map((t) => (
              <button key={t.id} onClick={() => setTab(t.id)}
                className={`seg-pill ${tab === t.id ? 'active' : ''}`}>
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {(health == null || !ok || warming || keyBad) && (
          <div className="status-pill">
            <span className={`w-2 h-2 rounded-full ${ok && !warming && !keyBad ? '' : 'animate-pulse'}`}
              style={{ background: !ok ? (health ? 'var(--red)' : 'var(--amber)') : keyBad ? 'var(--red)' : 'var(--amber)' }} />
            <span>
              {health == null ? 'Connecting'
                : !ok ? 'Backend offline'
                : warming ? 'Warming up'
                : selfTest?.capacity ? 'Model at capacity, retrying every minute. Scenario chips still work.'
                : 'Model credentials rejected. Scenario chips still work.'}
            </span>
          </div>
        )}
        <PersonaSelector />
      </div>
    </header>
  );
}

function Layout() {
  const [tab, setTab] = useState('landing');
  const page = () => {
    switch (tab) {
      case 'landing': return <LandingPage go={setTab} />;
      case 'assistant': return <AssistantPage />;
      case 'overview': return <DashboardOverview />;
      case 'simulator': return <SimulatorPage />;
      case 'ram': return <RamCopilotPage />;
      case 'evaluation': return <EvaluationPage />;
      case 'queue': return <QueuePage />;
      case 'documents': return <DocumentsPage />;
      case 'data': return <DataPage />;
      case 'audit': return <AuditPage />;
      default: return <LandingPage go={setTab} />;
    }
  };

  return (
    <div className="app-shell">
      <Bokeh />
      <Header tab={tab} setTab={setTab} />
      <main className="flex-1 min-h-0 relative z-[1]">
        {page()}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <Layout />
    </AppProvider>
  );
}
