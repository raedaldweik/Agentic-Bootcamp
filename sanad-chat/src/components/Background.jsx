/** Atmosphere: aurora blobs in Sanad blue + cyan, a fading dot grid and slow orbit lines. */
export default function Background() {
  return (
    <div className="sn-bg" aria-hidden="true">
      <div className="sn-aurora a" />
      <div className="sn-aurora b" />
      <div className="sn-aurora c" />
      <div className="sn-grid" />
      <svg className="sn-orbits" viewBox="0 0 1000 1000" fill="none">
        <g stroke="rgba(143,211,255,0.10)" strokeWidth="1">
          <ellipse cx="500" cy="500" rx="430" ry="290" />
          <ellipse cx="500" cy="500" rx="300" ry="440" transform="rotate(32 500 500)" />
          <circle cx="500" cy="500" r="478" strokeDasharray="4 16" />
        </g>
        <g fill="rgba(46,230,255,0.8)">
          <circle cx="930" cy="500" r="2.5" />
          <circle cx="500" cy="60" r="2" />
          <circle cx="70" cy="500" r="2.5" />
          <circle cx="760" cy="150" r="1.6" />
        </g>
      </svg>
    </div>
  );
}
