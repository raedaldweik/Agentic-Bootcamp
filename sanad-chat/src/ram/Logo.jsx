import { useId } from 'react';

// The three facets of the official Sanad S (SANAD_M_E_RGB_TRIANGLE.svg), each a
// horizontal gradient of one colour at different opacities, exactly as issued.
const FACETS = [
  { d: 'M27.1,108.8V37.1c0-5.5,4.5-9.9,10-9.9h131.8L27.1,108.8z', from: 0.3, to: 1 },
  { d: 'M27.1,108.8 L27.1,37.2 L168.9,118.8 L168.9,188.5 Z', from: 0.8, to: 0.3 },
  { d: 'M168.9,118.8v69.8c0,5.5-4.5,10-10,10H27.1L168.9,118.8z', from: 0.3, to: 0.6 },
];

/**
 * The Sanad "S" mark. `tone="navy"` is the official colour on light
 * surfaces (#071D49); `tone="white"` is the version used on Sanad's deep indigo.
 */
export function SanadMark({ size = 28, tone = 'navy', className = '', style }) {
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const color = tone === 'white' ? '#FFFFFF' : '#071D49';
  return (
    <svg width={size} height={size} viewBox="22 22 152 182" className={className} style={style} aria-hidden="true">
      <defs>
        {FACETS.map((f, i) => (
          <linearGradient key={i} id={`${uid}f${i}`} gradientUnits="userSpaceOnUse" x1="27.0877" y1="0" x2="168.9367" y2="0">
            <stop offset="0" stopColor={color} stopOpacity={f.from} />
            <stop offset="1" stopColor={color} stopOpacity={f.to} />
          </linearGradient>
        ))}
      </defs>
      {FACETS.map((f, i) => <path key={i} d={f.d} fill={`url(#${uid}f${i})`} />)}
    </svg>
  );
}

/**
 * Header logo, top left (where the hackathon app carries the EHS logo): the
 * official Sanad lockup, mark + wordmark + "A Mubadala Company".
 * VITE_LOGO_URL can point it at a hosted copy instead.
 */
export function Lockup() {
  // White on the dark frame, as on Sanad's event artwork
  const url = import.meta.env.VITE_LOGO_URL || '/sanad-logo-white.svg';
  return <img className="brand-logo" src={url} alt="Sanad — A Mubadala Company" />;
}
