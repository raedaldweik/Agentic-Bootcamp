import { useEffect, useState } from 'react';
import { AppProvider } from './context/AppContext';
import { getHealth, getLinks } from './services/api';
import LandingPage from './pages/LandingPage';
import AssistantPage from './pages/AssistantPage';
import DashboardOverview from './pages/DashboardOverview';
import DashboardMap from './pages/DashboardMap';
import SimulatorPage from './pages/SimulatorPage';
import DocumentsPage from './pages/DocumentsPage';
import DataPage from './pages/DataPage';
import RamCopilotPage from './ram/RamCopilotPage';
import ScreeningPage from './pages/ScreeningPage';
import ScreeningProgrammePage from './pages/ScreeningProgrammePage';
import ScreeningModelPage from './pages/ScreeningModelPage';
import ScreeningRulesPage from './pages/ScreeningRulesPage';
import ScreeningAgentPage from './pages/ScreeningAgentPage';
// Imported (not served from /public) so Vite gives it a hashed URL under /assets: a browser or edge
// cache can never show a stale copy of the logo after the file changes.
import sasLogoUrl from './assets/sas-logo.png';

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

// Four places to be: the home page, the two composite-AI examples, and the agent built on SAS RAM.
export const TABS = [
  { id: 'landing', label: 'Home' },
  { id: 'example', label: 'Population health' },
  { id: 'example2', label: 'Cancer screening' },
  { id: 'ram', label: 'SAS RAM' },
];

// Everything inside Population health: a second row of pills appears while one of them is open.
// The story order: the registry (the hook), the raw material (data, documents), the model, the agent.
export const EXAMPLE_TABS = [
  { id: 'overview', label: 'Registry' },
  { id: 'geography', label: 'Geography' },
  { id: 'data', label: 'Data' },
  { id: 'documents', label: 'Documents' },
  { id: 'simulator', label: 'Simulator' },
  { id: 'assistant', label: 'Agent' },
];
const EXAMPLE_IDS = EXAMPLE_TABS.map((t) => t.id);
const EXAMPLE_HOME = 'overview';

// Everything inside Cancer screening, told in order: the programme (the hook), the raw material the
// rules cite and the model learns from (data, documents), the policy as a decision flow, the
// prediction, one person through both, and the agent that brings it all together.
export const EXAMPLE2_TABS = [
  { id: 'crc_programme', label: 'Programme' },
  { id: 'crc_data', label: 'Data' },
  { id: 'crc_documents', label: 'Documents' },
  { id: 'crc_rules', label: 'Rules' },
  { id: 'crc_model', label: 'Model' },
  { id: 'screening', label: 'Screening check' },
  { id: 'crc_agent', label: 'Agent' },
];
const EXAMPLE2_IDS = EXAMPLE2_TABS.map((t) => t.id);
const EXAMPLE2_HOME = 'crc_programme';

function Header({ tab, setTab }) {
  const [health, setHealth] = useState(null);
  const [brandLogo, setBrandLogo] = useState(sasLogoUrl);
  useEffect(() => {
    let timer;
    const tick = () => getHealth().then((h) => {
      setHealth(h);
      // keep polling until the agent graph has warmed up (or the key has failed)
      if (h?.mode === 'multi-agent' && !h.warmup?.ready) timer = setTimeout(tick, 3000);
    }).catch(() => setHealth({ status: 'down' }));
    tick();
    // A hosted logo can be plugged in through LOGO_URL without a rebuild.
    getLinks().then((r) => {
      if (r?.branding?.logo_url) setBrandLogo(r.branding.logo_url);
    }).catch(() => {});
    return () => clearTimeout(timer);
  }, []);
  const ok = health?.status === 'ok';
  const selfTest = health?.warmup?.self_test;
  const warming = ok && health.mode === 'multi-agent' && !health.warmup?.ready;
  const keyBad = ok && health.mode === 'multi-agent' && selfTest && !selfTest.ok;
  const isExample = EXAMPLE_IDS.includes(tab);
  const isExample2 = EXAMPLE2_IDS.includes(tab);
  const activeTop = isExample ? 'example' : isExample2 ? 'example2' : tab;
  const goTop = (id) => setTab(id === 'example' ? EXAMPLE_HOME : id === 'example2' ? EXAMPLE2_HOME : id);
  const subTabs = isExample ? EXAMPLE_TABS : isExample2 ? EXAMPLE2_TABS : null;

  return (
    <header className="app-header">
      <button onClick={() => setTab('landing')} title="Home">
        <img className="brand-logo" src={brandLogo} alt="SAS"
          onError={(e) => { if (e.target.src !== sasLogoUrl) e.target.src = sasLogoUrl; }} />
      </button>

      <div className="title-block">
        <div className="header-eyebrow">SAS · Composite AI</div>
        <div className="title-row">
          <h1 className="app-title">
            <b>Composite AI in Health Care</b>
          </h1>
          <div className="accent-line" />
        </div>
        <div className="nav-row">
          <div className="seg-track">
            {TABS.map((t) => (
              <button key={t.id} onClick={() => goTop(t.id)}
                className={`seg-pill ${activeTop === t.id ? 'active' : ''}`}>
                {t.label}
              </button>
            ))}
          </div>
          {subTabs && (
            <>
              <span className="nav-divider" />
              <div className="seg-track">
                {subTabs.map((t) => (
                  <button key={t.id} onClick={() => setTab(t.id)}
                    className={`seg-pill ${tab === t.id ? 'active' : ''}`}>
                    {t.label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="flex items-center gap-4">
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
      case 'landing': return <LandingPage onNavigate={setTab} />;
      case 'overview': return <DashboardOverview />;
      case 'geography': return <DashboardMap />;
      case 'simulator': return <SimulatorPage />;
      case 'data': return <DataPage />;
      case 'documents': return <DocumentsPage />;
      case 'assistant': return <AssistantPage />;
      case 'screening': return <ScreeningPage />;
      case 'crc_programme': return <ScreeningProgrammePage onOpenAgent={() => setTab('crc_agent')} />;
      case 'crc_model': return <ScreeningModelPage />;
      case 'crc_rules': return <ScreeningRulesPage />;
      case 'crc_data': return <DataPage source="screening" />;
      case 'crc_documents': return <DocumentsPage source="screening" />;
      case 'crc_agent': return <ScreeningAgentPage />;
      case 'ram': return <RamCopilotPage />;
      default: return <LandingPage onNavigate={setTab} />;
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
