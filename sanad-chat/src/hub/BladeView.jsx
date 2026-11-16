// The blade inspection view: one fan blade, its three leading-edge zones, and each
// zone's measurement against the limit.
const COLOR = { within: '#0E8A5F', above: '#C4283A' };

const ZONE_Y = { A: 54, B: 150, C: 246 };          // tip, mid-span, root (top to bottom)

export default function BladeView({ b }) {
  const zones = b.zones || [];
  const max = Math.max(...zones.map((z) => Math.max(z.result_mm ?? 0, z.limit_mm ?? 0)), 0.01) * 1.15;
  return (
    <div className="hub-blade">
      <svg viewBox="0 0 250 300" className="hub-blade-svg" role="img" aria-label={`Blade ${b.serial}: ${b.damage}`}>
        <defs>
          <linearGradient id="bladeFill" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0" stopColor="#C9D6E4" /><stop offset="0.45" stopColor="#F3F7FB" /><stop offset="1" stopColor="#A9BCCF" />
          </linearGradient>
          <linearGradient id="rootFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="#9FB2C6" /><stop offset="1" stopColor="#71879E" />
          </linearGradient>
        </defs>
        {/* blade body: a twisted aerofoil, leading edge on the left */}
        <path d="M92 14 C120 8 150 12 168 22 C186 70 190 150 172 262 L104 262 C82 190 74 96 92 14 Z" fill="url(#bladeFill)" stroke="#6B8199" strokeWidth="1.4" />
        <path d="M128 16 C142 80 142 180 132 262" fill="none" stroke="#8FA4BA" strokeWidth="0.9" strokeDasharray="3 4" />
        {/* root / dovetail */}
        <path d="M96 262 L180 262 L188 280 L172 290 L104 290 L88 280 Z" fill="url(#rootFill)" stroke="#5B7088" strokeWidth="1.2" />
        {/* leading edge */}
        <path d="M92 14 C74 96 82 190 104 262" fill="none" stroke="#2F6FA8" strokeWidth="2.6" strokeLinecap="round" />
        <text x="20" y="20" className="hub-blade-note">Leading edge</text>
        <path d="M70 24 L86 34" stroke="#4F6178" strokeWidth="0.9" />
        {zones.map((z) => {
          const y = ZONE_Y[z.zone] ?? 150;
          const x = z.zone === 'A' ? 84 : z.zone === 'B' ? 80 : 97;
          const c = COLOR[z.status] || '#2F6FA8';
          return (
            <g key={z.zone}>
              {z.status === 'above' && <circle cx={x} cy={y} r="15" fill={c} opacity="0.16"><animate attributeName="r" values="11;17;11" dur="2.2s" repeatCount="indefinite" /></circle>}
              <circle cx={x} cy={y} r="8.5" fill="#fff" stroke={c} strokeWidth="2.4" />
              <text x={x} y={y + 3.6} textAnchor="middle" className="hub-blade-zone" fill={c}>{z.zone}</text>
              <path d={`M${x + 10} ${y} L 200 ${y}`} stroke={c} strokeWidth="1" strokeDasharray="2 3" opacity="0.7" />
              <text x="204" y={y - 3} className="hub-blade-zone-name" fill={c}>{z.name}</text>
              <text x="204" y={y + 10} className="hub-blade-note">{Number(z.result_mm).toFixed(2)} mm</text>
            </g>
          );
        })}
        <text x="138" y="282" textAnchor="middle" className="hub-blade-note" fill="#fff">Root</text>
      </svg>

      <div className="hub-blade-zones">
        <div className="hub-blade-serial">Blade S/N <b>{b.serial}</b> · {b.damage}</div>
        {zones.map((z) => {
          const over = z.status === 'above';
          return (
            <div key={z.zone} className={`hub-zone ${over ? 'is-over' : ''}`}>
              <div className="hub-zone-head">
                <span className="hub-zone-badge" style={{ borderColor: COLOR[z.status], color: COLOR[z.status] }}>{z.zone}</span>
                <div className="min-w-0 flex-1">
                  <div className="hub-zone-name">{z.name} <span>· {z.location}</span></div>
                </div>
                <span className={`hub-pill tone-${over ? 'bad' : 'good'}`}>{over ? 'Above limit' : 'Within limit'}</span>
              </div>
              <div className="hub-zone-bar">
                <div className="hub-zone-fill" style={{ width: `${Math.min(100, (z.result_mm / max) * 100)}%`, background: COLOR[z.status] }} />
                <div className="hub-zone-limit" style={{ left: `${(z.limit_mm / max) * 100}%` }} title={`Limit ${z.limit_mm} mm`} />
              </div>
              <div className="hub-zone-figures">
                <span>Measured <b>{Number(z.result_mm).toFixed(2)} mm</b></span>
                <span>Limit ≤ {Number(z.limit_mm).toFixed(2)} mm</span>
              </div>
              {z.caution && <div className="hub-zone-caution">{z.caution}</div>}
            </div>
          );
        })}
        <div className="hub-blade-standard">{b.standard}</div>
      </div>
    </div>
  );
}
