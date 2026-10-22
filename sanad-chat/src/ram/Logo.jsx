import { useStrings } from '../lib/strings';

/**
 * The Sanad "S" — a geometric uppercase letterform built from two structured
 * forms, upper and lower, that overlap through the middle band; the overlap
 * is drawn in a deeper tone (the transparency effect of the identity).
 */
export function SanadMark({ size = 28, className = '', style }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" className={className} style={style} aria-hidden="true">
      <path d="M60 4 H12 V39 H52 V29 H22 V14 H55 Z" fill="#2C72E0" />
      <path d="M4 60 H52 V25 H12 V35 H42 V50 H9 Z" fill="#0B5BD3" />
      <path d="M12 25 H22 V29 H52 V39 H42 V35 H12 Z" fill="#083F9A" />
    </svg>
  );
}

/**
 * Header lockup, top left (where the hackathon app carries the EHS logo).
 * Set VITE_LOGO_URL (for example /sanad-logo.svg after dropping the official
 * file into public/) to show the official artwork instead.
 */
export function Lockup() {
  const { t } = useStrings();
  const url = import.meta.env.VITE_LOGO_URL;
  if (url) return <img className="brand-logo" src={url} alt="Sanad" />;
  return (
    <div className="brand-lockup" title="Sanad">
      <SanadMark size={44} className="brand-mark" />
      <div>
        <div className="brand-word">SANAD</div>
        <div className="brand-sub">{t('mubadala')}</div>
      </div>
    </div>
  );
}
