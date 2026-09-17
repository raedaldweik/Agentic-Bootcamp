import { useEffect, useState } from 'react';
import { AppProvider } from './context/AppContext';
import { getHealth, getLinks } from './services/api';
import LandingPage from './pages/LandingPage';
import AssistantPage from './pages/AssistantPage';
import DashboardOverview from './pages/DashboardOverview';
import DocumentsPage from './pages/DocumentsPage';
import DataPage from './pages/DataPage';
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

export const TABS = [
  { id: 'landing', label: 'Home' },
  { id: 'overview', label: 'Dashboard' },
  { id: 'data', label: 'Data' },
  { id: 'documents', label: 'Documents' },
  { id: 'assistant', label: 'Assistant' },
  { id: 'ram', label: 'SAS RAM' },
];

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

  return (
    <header className="app-header">
      <button onClick={() => setTab('landing')} title="Home">
        <img className="brand-logo" src={ehsLogo} alt="Emirates Health Services"
          onError={(e) => { if (e.target.src.indexOf('/ehs-logo.png') === -1) e.target.src = '/ehs-logo.png'; }} />
      </button>

      <div className="title-block">
        <div className="header-eyebrow">Emirates Health Services × SAS</div>
        <div className="title-row">
          <h1 className="app-title">
            <b>Agentic AI Bootcamp</b> <span className="title-sep">·</span> SAS Retrieval Agent Manager
          </h1>
          <div className="accent-line" />
        </div>
        <div className="nav-row">
          <div className="seg-track">
            {TABS.map((t) => (
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
      </div>
    </header>
  );
}

function Layout() {
  const [tab, setTab] = useState('landing');
  const page = () => {
    switch (tab) {
      case 'landing': return <LandingPage />;
      case 'overview': return <DashboardOverview />;
      case 'data': return <DataPage />;
      case 'documents': return <DocumentsPage />;
      case 'assistant': return <AssistantPage />;
      case 'ram': return <RamCopilotPage />;
      default: return <LandingPage />;
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
