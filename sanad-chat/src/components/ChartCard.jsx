import { useMemo, useRef, useState } from 'react';

/*
 * ChartCard — renders a `render_chart` spec (kind:"chart") as an interactive,
 * dependency-free SVG chart in the Sanad palette. Supports bar, line, area,
 * pie and scatter, multiple series, stacking, and hover tooltips.
 * `yKeys` entries may be plain column names or objects ({ key, label }).
 */

const PALETTE = ['#4FA3FF', '#2EE6FF', '#E8B65A', '#A78BFA', '#35E0A1', '#FF7A9E', '#8FD3FF', '#F97316', '#60A5FA', '#C084FC'];

const VB_W = 720;
const VB_H = 380;
const M = { top: 18, right: 20, bottom: 70, left: 60 };
const PLOT_W = VB_W - M.left - M.right;
const PLOT_H = VB_H - M.top - M.bottom;
const GRID = 'rgba(143,211,255,0.10)';
const AXIS = 'rgba(143,211,255,0.28)';
const TICK = '#6F86AE';
const LABEL = '#9FB3D6';

function num(v) {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  if (v == null) return null;
  const n = parseFloat(String(v).replace(/[, %]/g, ''));
  return Number.isFinite(n) ? n : null;
}
function fmt(v) {
  if (v == null) return '—';
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return (Math.round(n * 100) / 100).toLocaleString(undefined, { maximumFractionDigits: 2 });
}
function niceMax(max) {
  if (max <= 0) return 1;
  const pow = Math.pow(10, Math.floor(Math.log10(max)));
  const n = max / pow;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return step * pow;
}
function normKey(k) {
  if (k == null) return null;
  if (typeof k === 'string' || typeof k === 'number') return { key: String(k), label: String(k) };
  if (typeof k === 'object' && k.key != null) return { key: String(k.key), label: k.label || k.name || String(k.key) };
  return null;
}

export default function ChartCard({ spec }) {
  const wrapRef = useRef(null);
  const [hover, setHover] = useState(null);

  const type = (spec?.type || 'bar').toLowerCase();
  const rows = Array.isArray(spec?.data) ? spec.data : [];
  const xKey = spec?.xKey;
  const yKeys = useMemo(() => (Array.isArray(spec?.yKeys) ? spec.yKeys.map(normKey).filter(Boolean) : []), [spec?.yKeys]);
  const stacked = !!spec?.stacked;
  const series = useMemo(() => yKeys.map((k, i) => ({
    key: k.key, label: k.label, color: PALETTE[i % PALETTE.length], vals: rows.map((r) => num(r?.[k.key])),
  })), [rows, yKeys]);

  if (!rows.length || !series.length) return null;

  const labels = rows.map((r, i) => { const v = r?.[xKey]; return v == null || v === '' ? `#${i + 1}` : String(v); });
  const moveTip = (e, label, items) => {
    const rect = wrapRef.current?.getBoundingClientRect();
    if (!rect) return;
    setHover({ x: e.clientX - rect.left, y: e.clientY - rect.top, label, items });
  };
  const clearTip = () => setHover(null);

  return (
    <div className="cc-wrap a-slide-up">
      <div className="cc-title">{spec.title || 'Chart'}</div>
      {spec.subtitle ? <div className="cc-sub">{spec.subtitle}</div> : null}
      <div className="cc-plot" ref={wrapRef}>
        <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="cc-svg" role="img" aria-label={spec.title || 'chart'}>
          {type === 'pie'
            ? <Pie labels={labels} series={series} onHover={moveTip} onLeave={clearTip} />
            : <Cartesian type={type} labels={labels} series={series} stacked={stacked} onHover={moveTip} onLeave={clearTip} />}
        </svg>
        {hover && (
          <div className="cc-tip" style={{ left: hover.x, top: hover.y }}>
            <div className="cc-tip-label">{hover.label}</div>
            {hover.items.map((it, i) => (
              <div key={i} className="cc-tip-row">
                <span className="cc-tip-dot" style={{ background: it.color }} />
                <span className="cc-tip-name">{it.name}</span>
                <span className="cc-tip-val">{fmt(it.value)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      {(series.length > 1 || type === 'pie' || series[0].label !== series[0].key) && (
        <div className="cc-legend">
          {(type === 'pie' ? labels : series.map((s) => s.label)).map((name, i) => (
            <span key={i} className="cc-leg-item"><span className="cc-leg-dot" style={{ background: PALETTE[i % PALETTE.length] }} />{name}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function Cartesian({ type, labels, series, stacked, onHover, onLeave }) {
  const n = labels.length;
  const bandW = PLOT_W / Math.max(n, 1);
  let yMax; let yMin = 0;
  if ((type === 'bar' || type === 'area') && stacked && series.length > 1) {
    yMax = Math.max(0, ...labels.map((_, i) => series.reduce((sum, s) => sum + (s.vals[i] || 0), 0)));
  } else {
    const all = series.flatMap((s) => s.vals).filter((v) => v != null);
    yMax = all.length ? Math.max(...all) : 1;
    yMin = Math.min(0, ...(all.length ? all : [0]));
  }
  yMax = niceMax(yMax || 1);
  const span = yMax - yMin || 1;
  const yPix = (v) => M.top + PLOT_H - ((v - yMin) / span) * PLOT_H;
  const xCenter = (i) => M.left + bandW * (i + 0.5);
  const ticks = Array.from({ length: 5 }, (_, t) => yMin + (span * t) / 4);
  const rotate = n > 6 || labels.some((l) => l.length > 6);
  const itemsAt = (i) => series.map((s) => ({ name: s.label, color: s.color, value: s.vals[i] }));

  return (
    <>
      {ticks.map((tv, t) => (
        <g key={t}>
          <line x1={M.left} x2={M.left + PLOT_W} y1={yPix(tv)} y2={yPix(tv)} stroke={GRID} strokeWidth="1" />
          <text x={M.left - 8} y={yPix(tv) + 3} textAnchor="end" fontSize="11" fill={TICK}>{fmt(tv)}</text>
        </g>
      ))}
      <line x1={M.left} x2={M.left} y1={M.top} y2={M.top + PLOT_H} stroke={AXIS} />
      <line x1={M.left} x2={M.left + PLOT_W} y1={M.top + PLOT_H} y2={M.top + PLOT_H} stroke={AXIS} />
      {type === 'bar' && <Bars {...{ series, stacked, bandW, xCenter, yPix, yMin }} />}
      {(type === 'line' || type === 'area') && <Lines {...{ type, series, xCenter, yPix, yMin }} />}
      {type === 'scatter' && <Scatter {...{ series, xCenter, yPix }} />}
      {labels.map((lab, i) => (
        <text key={i} x={xCenter(i)} y={M.top + PLOT_H + (rotate ? 14 : 18)} textAnchor={rotate ? 'end' : 'middle'} fontSize="11" fill={LABEL}
          transform={rotate ? `rotate(-35 ${xCenter(i)} ${M.top + PLOT_H + 14})` : undefined}>
          {lab.length > 14 ? `${lab.slice(0, 13)}…` : lab}
        </text>
      ))}
      {labels.map((lab, i) => (
        <rect key={i} x={M.left + bandW * i} y={M.top} width={bandW} height={PLOT_H} fill="transparent" style={{ cursor: 'crosshair' }}
          onMouseMove={(e) => onHover(e, lab, itemsAt(i))} onMouseLeave={onLeave} />
      ))}
    </>
  );
}

function Bars({ series, stacked, bandW, xCenter, yPix, yMin }) {
  const slot = bandW * 0.68;
  const out = [];
  series.forEach((s, si) => {
    s.vals.forEach((v, i) => {
      if (v == null) return;
      let x; let y; let h;
      if (stacked && series.length > 1) {
        const below = series.slice(0, si).reduce((sum, p) => sum + (p.vals[i] || 0), 0);
        x = xCenter(i) - slot / 2;
        const yTop = yPix(below + v);
        y = yTop; h = yPix(below) - yTop;
      } else {
        const bw = slot / series.length;
        x = xCenter(i) - slot / 2 + si * bw;
        const base = yPix(Math.max(yMin, 0));
        const yTop = yPix(v);
        y = Math.min(base, yTop); h = Math.abs(base - yTop);
      }
      const w = stacked && series.length > 1 ? slot : slot / series.length;
      out.push(<rect key={`${si}-${i}`} x={x + 1} y={y} width={Math.max(w - 2, 1)} height={Math.max(h, 0)} rx="3" fill={s.color} opacity="0.88" />);
    });
  });
  return <g>{out}</g>;
}

function Lines({ type, series, xCenter, yPix, yMin }) {
  return (
    <g>
      {series.map((s, si) => {
        const pts = s.vals.map((v, i) => (v == null ? null : [xCenter(i), yPix(v)]));
        const segs = pts.filter(Boolean);
        if (!segs.length) return null;
        const line = segs.map((p, i) => `${i ? 'L' : 'M'}${p[0]},${p[1]}`).join(' ');
        const base = yPix(Math.max(yMin, 0));
        const areaPath = `${line} L${segs[segs.length - 1][0]},${base} L${segs[0][0]},${base} Z`;
        return (
          <g key={si}>
            {type === 'area' && <path d={areaPath} fill={s.color} opacity="0.14" />}
            <path d={line} fill="none" stroke={s.color} strokeWidth="2.6" strokeLinejoin="round" strokeLinecap="round"
              style={{ filter: `drop-shadow(0 0 5px ${s.color}88)` }} />
            {segs.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="3.4" fill="#061330" stroke={s.color} strokeWidth="2" />)}
          </g>
        );
      })}
    </g>
  );
}

function Scatter({ series, xCenter, yPix }) {
  const s = series[0];
  return <g>{s.vals.map((v, i) => (v == null ? null : <circle key={i} cx={xCenter(i)} cy={yPix(v)} r="5" fill={s.color} opacity="0.8" />))}</g>;
}

function Pie({ labels, series, onHover, onLeave }) {
  const s = series[0];
  const vals = s.vals.map((v) => (v && v > 0 ? v : 0));
  const total = vals.reduce((a, b) => a + b, 0) || 1;
  const cx = M.left + PLOT_W / 2;
  const cy = M.top + PLOT_H / 2;
  const r = Math.min(PLOT_W, PLOT_H) / 2 - 6;
  const ri = r * 0.52; // donut
  let a0 = -Math.PI / 2;
  const arcs = vals.map((v, i) => {
    const a1 = a0 + (v / total) * Math.PI * 2;
    const big = a1 - a0 > Math.PI ? 1 : 0;
    const p = (rad, a) => [cx + rad * Math.cos(a), cy + rad * Math.sin(a)];
    const [x0, y0] = p(r, a0); const [x1, y1] = p(r, a1);
    const [ix0, iy0] = p(ri, a0); const [ix1, iy1] = p(ri, a1);
    const mid = (a0 + a1) / 2;
    const path = v <= 0 ? null
      : `M${x0},${y0} A${r},${r} 0 ${big} 1 ${x1},${y1} L${ix1},${iy1} A${ri},${ri} 0 ${big} 0 ${ix0},${iy0} Z`;
    const seg = { path, color: PALETTE[i % PALETTE.length], label: labels[i], value: v, pct: (v / total) * 100,
      lx: cx + (r + ri) / 2 * Math.cos(mid), ly: cy + (r + ri) / 2 * Math.sin(mid) };
    a0 = a1;
    return seg;
  });
  return (
    <g>
      {arcs.map((seg, i) => seg.path && (
        <path key={i} d={seg.path} fill={seg.color} opacity="0.9" stroke="#061330" strokeWidth="2" style={{ cursor: 'pointer' }}
          onMouseMove={(e) => onHover(e, seg.label, [{ name: `${seg.pct.toFixed(1)}%`, color: seg.color, value: seg.value }])} onMouseLeave={onLeave} />
      ))}
      {arcs.map((seg, i) => seg.path && seg.pct >= 6 && (
        <text key={`l${i}`} x={seg.lx} y={seg.ly + 4} textAnchor="middle" fontSize="12" fontWeight="700" fill="#03091A">{`${seg.pct.toFixed(0)}%`}</text>
      ))}
      <text x={cx} y={cy - 4} textAnchor="middle" fontSize="11" fill={TICK}>{s.label}</text>
      <text x={cx} y={cy + 16} textAnchor="middle" fontSize="18" fontWeight="700" fill="#EEF4FF">{fmt(total)}</text>
    </g>
  );
}
