import { useEffect, useState } from 'react';
import { AppProvider, useApp } from './context/AppContext';
import TeamGate from './components/TeamGate';
import { getHealth, getLinks } from './services/api';
import LandingPage from './pages/LandingPage';
import AssistantPage from './pages/AssistantPage';
import DashboardOverview from './pages/DashboardOverview';
import DashboardMap from './pages/DashboardMap';
import SimulatorPage from './pages/SimulatorPage';
import DocumentsPage from './pages/DocumentsPage';
import DataPage from './pages/DataPage';
import RamCopilotPage from './ram/RamCopilotPage';
// Imported (not served from /public) so Vite gives it a hashed URL under /assets: a browser or edge
// cache can never show a stale copy of the partner mark after the file changes.
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

// Three places to be: the home page, the finished example to learn from, and the agent you build.
export const TABS = [
  { id: 'landing', label: 'Home' },
  { id: 'example', label: 'Example 1' },
  { id: 'ram', label: 'Hackathon Agent' },
];

// Everything inside Example 1: a second row of pills appears while one of them is open.
export const EXAMPLE_TABS = [
  { id: 'overview', label: 'Registry' },
  { id: 'geography', label: 'Geography' },
  { id: 'simulator', label: 'Simulator' },
  { id: 'data', label: 'Data' },
  { id: 'documents', label: 'Documents' },
  { id: 'assistant', label: 'Example agent' },
];
const EXAMPLE_IDS = EXAMPLE_TABS.map((t) => t.id);
const EXAMPLE_HOME = 'overview';

function Header({ tab, setTab }) {
  const { team, teamsEnabled, signOutTeam, openGate } = useApp();
  const [health, setHealth] = useState(null);
  const [ehsLogo, setEhsLogo] = useState('/ehs-logo.png');
  const [sasLogo, setSasLogo] = useState(sasLogoUrl);
  useEffect(() => {
    let timer;
    const tick = () => getHealth().then((h) => {
      setHealth(h);
      // keep polling until the agent graph has warmed up (or the key has failed)
      if (h?.mode === 'multi-agent' && !h.warmup?.ready) timer = setTimeout(tick, 3000);
    }).catch(() => setHealth({ status: 'down' }));
    tick();
    // A hosted logo can be plugged in through EHS_LOGO_URL without a rebuild.
    getLinks().then((r) => {
      if (r?.branding?.ehs_logo_url) setEhsLogo(r.branding.ehs_logo_url);
      if (r?.branding?.sas_logo_url) setSasLogo(r.branding.sas_logo_url);
    }).catch(() => {});
    return () => clearTimeout(timer);
  }, []);
  const ok = health?.status === 'ok';
  const selfTest = health?.warmup?.self_test;
  const warming = ok && health.mode === 'multi-agent' && !health.warmup?.ready;
  const keyBad = ok && health.mode === 'multi-agent' && selfTest && !selfTest.ok;
  const isExample = EXAMPLE_IDS.includes(tab);
  const activeTop = isExample ? 'example' : tab;
  const goTop = (id) => setTab(id === 'example' ? EXAMPLE_HOME : id);

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
            <b>Agentic AI Hackathon</b>
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
          {isExample && (
            <>
              <span className="nav-divider" />
              <div className="seg-track">
                {EXAMPLE_TABS.map((t) => (
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
        {teamsEnabled && (team ? (
          <button className="team-chip" onClick={() => { signOutTeam(); setTab('landing'); }}
            title="Signed in as this team: its Viya and RAM. Click to switch team.">
            {team.name} <span className="team-chip-sub">switch</span>
          </button>
        ) : (
          <button className="team-chip unset" onClick={openGate} title="Sign in as your team to use its Viya and RAM">
            Sign in as a team
          </button>
        ))}
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
        <img className="partner-logo" src={sasLogo} alt="SAS"
          onError={(e) => { if (e.target.src !== sasLogoUrl) e.target.src = sasLogoUrl; }} />
      </div>
    </header>
  );
}

function Layout() {
  const [tab, setTab] = useState('landing');
  const { team } = useApp();
  const page = () => {
    switch (tab) {
      case 'landing': return <LandingPage />;
      case 'overview': return <DashboardOverview />;
      case 'geography': return <DashboardMap />;
      case 'simulator': return <SimulatorPage />;
      case 'data': return <DataPage />;
      case 'documents': return <DocumentsPage />;
      case 'assistant': return <AssistantPage />;
      case 'ram': return <RamCopilotPage key={team?.id || 'one'} />;  // a new team means a new RAM: start the page over
      default: return <LandingPage />;
    }
  };

  return (
    <div className="app-shell">
      <Bokeh />
      <TeamGate />
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
