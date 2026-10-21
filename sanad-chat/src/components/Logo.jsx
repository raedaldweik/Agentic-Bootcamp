import { useId } from 'react';
import { useLanguage } from '../lib/LanguageContext';

/** The Sanad "S" — a sharp, structured geometric letterform in the brand blue gradient. */
export function SanadMark({ size = 28, className = '', style }) {
  const id = useId();
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" className={className} style={style} aria-hidden="true">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2EE6FF" />
          <stop offset="0.55" stopColor="#3B8BFF" />
          <stop offset="1" stopColor="#0B5BD3" />
        </linearGradient>
      </defs>
      <path d="M14 8 H58 L52 20 H26 V26 H54 V56 H6 L12 44 H42 V38 H14 Z" fill={`url(#${id})`} />
    </svg>
  );
}

/**
 * Brand lockup for the rail. Set VITE_LOGO_URL (for example /sanad-logo.svg
 * after dropping the official file into public/) to show the official
 * artwork instead of the built-in mark + wordmark.
 */
export function Lockup({ compact = false }) {
  const { t } = useLanguage();
  const url = import.meta.env.VITE_LOGO_URL;
  if (url && !compact) {
    return <img src={url} alt="Sanad" style={{ height: 36, width: 'auto', display: 'block' }} />;
  }
  return (
    <div className="sn-lockup">
      <div className="sn-mark-tile"><SanadMark size={22} /></div>
      {!compact && (
        <div className="min-w-0">
          <div className="sn-wordmark">SANAD</div>
          <div className="sn-wordsub">{t('mubadala')}</div>
        </div>
      )}
    </div>
  );
}

/** A slowly turning turbine disc — the welcome screen's backdrop. */
export function Turbine({ blades = 48 }) {
  const cx = 300, cy = 300, inner = 128, outer = 282;
  return (
    <svg viewBox="0 0 600 600" fill="none" aria-hidden="true">
      <circle cx={cx} cy={cy} r={outer} stroke="rgba(143,211,255,0.22)" strokeWidth="1" />
      <circle cx={cx} cy={cy} r={outer - 10} stroke="rgba(143,211,255,0.10)" strokeWidth="1" strokeDasharray="3 9" />
      <circle cx={cx} cy={cy} r={inner} stroke="rgba(143,211,255,0.28)" strokeWidth="1.2" />
      <circle cx={cx} cy={cy} r={inner - 14} stroke="rgba(46,230,255,0.18)" strokeWidth="1" />
      <circle cx={cx} cy={cy} r={28} fill="rgba(46,230,255,0.06)" stroke="rgba(46,230,255,0.35)" strokeWidth="1" />
      {Array.from({ length: blades }, (_, i) => (
        <path key={i}
          d={`M ${cx} ${cy - inner} Q ${cx + 22} ${cy - (inner + outer) / 2} ${cx + 6} ${cy - outer}`}
          stroke={i % 6 === 0 ? 'rgba(46,230,255,0.7)' : 'rgba(143,211,255,0.42)'}
          strokeWidth={i % 6 === 0 ? 1.8 : 1.1}
          strokeLinecap="round"
          transform={`rotate(${(360 / blades) * i} ${cx} ${cy})`} />
      ))}
    </svg>
  );
}
