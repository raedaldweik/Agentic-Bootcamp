import { useCallback, useEffect, useState } from 'react';
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
   showcase when this is a static preview). The label on screen follows what is really there.
   A server that cannot be reached shows a retry, never a different application. */
function Unreachable({ onRetry, trying }) {
  return (
    <div className="h-full flex items-center justify-center p-6">
      <div className="glass-card p-7 w-full max-w-[420px] text-center">
        <h2 className="text-[17px] font-extrabold mb-1" style={{ color: 'var(--text)' }}>The assistant can't be reached</h2>
        <p className="text-[12.5px] leading-relaxed mb-4" style={{ color: 'var(--text-dim)' }}>
          It may be starting or restarting. This page tries again by itself every few seconds.
        </p>
        <button onClick={onRetry} disabled={trying} className="px-5 py-2 rounded-lg text-[12.5px] font-bold text-white"
          style={{ background: 'var(--brand-grad)', opacity: trying ? 0.6 : 1 }}>{trying ? 'Trying…' : 'Try now'}</button>
      </div>
    </div>
  );
}

export default function App() {
  const [mode, setMode] = useState(null);         // null while asking · { kind: 'hub', health } · { kind: 'ram' } · { kind: 'down' }
  const [trying, setTrying] = useState(true);
  const look = useCallback(() => {
    setTrying(true);
    detect().then((m) => { setMode(m); setTrying(false); });
  }, []);
  useEffect(() => { look(); }, [look]);
  useEffect(() => {
    if (mode?.kind !== 'down') return undefined;
    const timer = setTimeout(look, 5000);
    return () => clearTimeout(timer);
  }, [mode, look]);
  useEffect(() => { if (mode?.kind !== 'ram') document.title = 'Sanad MRO Intelligence Hub'; }, [mode]);
  return (
    <div className="app-shell">
      <Bokeh />
      <Header hub={mode?.kind !== 'ram'} />
      <main className="flex-1 min-h-0 relative z-[1]">
        {mode?.kind === 'hub' && <HubPage health={mode.health} />}
        {mode?.kind === 'ram' && <RamPage />}
        {mode?.kind === 'down' && <Unreachable onRetry={look} trying={trying} />}
      </main>
    </div>
  );
}
