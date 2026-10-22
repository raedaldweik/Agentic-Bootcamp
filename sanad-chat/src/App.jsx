import RamPage from './ram/RamPage';
import { Lockup } from './ram/Logo';
import { useStrings } from './lib/strings';

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
function Header() {
  const { t } = useStrings();
  return (
    <header className="app-header">
      <Lockup />
      <div className="title-block">
        <div className="header-eyebrow">{t('eyebrow')}</div>
        <div className="title-row">
          <h1 className="app-title"><b>{t('appTitle')}</b></h1>
          <div className="accent-line" />
        </div>
      </div>
      <div />
    </header>
  );
}

export default function App() {
  return (
    <div className="app-shell">
      <Bokeh />
      <Header />
      <main className="flex-1 min-h-0 relative z-[1]">
        <RamPage />
      </main>
    </div>
  );
}
