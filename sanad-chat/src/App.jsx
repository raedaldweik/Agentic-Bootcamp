import { useEffect, useState } from 'react';
import RamPage from './ram/RamPage';
import HubPage from './hub/HubPage';
import { Lockup } from './ram/Logo';
import { useStrings } from './lib/strings';
import { detect } from './lib/hubApi';

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

/* The hackathon header: brand lockup top left, eyebrow + title + accent line. No partner logo. */
function Header({ hub }) {
  const { t } = useStrings();
  return (
    <header className="app-header">
      <Lockup />
      <div className="title-block">
        <div className="header-eyebrow">{hub ? t('hubEyebrow') : t('eyebrow')}</div>
        <div className="title-row">
          <h1 className="app-title"><b>{hub ? t('hubTitle') : t('appTitle')}</b></h1>
          <div className="accent-line" />
        </div>
      </div>
      <div />
    </header>
  );
}

/* Which assistant is behind the chat is decided once, by asking the server: the built-in
   Sanad Digital Assistant when it is served, otherwise SAS Retrieval Agent Manager (or the
   showcase when nothing answers). The label on screen follows what is really there. */
export default function App() {
  const [mode, setMode] = useState(null);         // null while asking · { hub: health } · { ram: true }
  useEffect(() => { detect().then((health) => setMode(health ? { hub: health } : { ram: true })); }, []);
  useEffect(() => { if (mode?.hub) document.title = 'Sanad MRO Intelligence Hub'; }, [mode]);
  return (
    <div className="app-shell">
      <Bokeh />
      <Header hub={!mode || !!mode.hub} />
      <main className="flex-1 min-h-0 relative z-[1]">
        {mode?.hub && <HubPage health={mode.hub} />}
        {mode?.ram && <RamPage />}
      </main>
    </div>
  );
}
