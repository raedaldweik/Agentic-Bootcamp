import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Cell, Tooltip, ReferenceLine, LabelList } from 'recharts';
import { getCrcModel, getCrcProfile, getCrcProfilePreset, getCrcProfiles, postCrcSimulate, streamCrcExplain } from '../services/api';
import { Panel, Spinner } from '../components/ui';
import { Lever, Stat } from './SimulatorPage';

/*
 * Cancer screening, the model: the one predictive layer in the composite, on anonymous profiles.
 *   Left    · the factors you can move (access, engagement, profile)
 *   Centre  · the model's estimate before and after, the band, and the ONE rule the band feeds (outreach, §8.3)
 *   Right   · what moved the estimate (attribution) and the narrated explanation; the model card below
 * Same visual language as the population-health story's simulator; the model never touches eligibility or the test.
 */

const BAND_COLOR = { Low: '#3a8e5a', Moderate: '#b8862e', High: '#d97706', 'Very high': '#b03c3c' };
const UP = '#b03c3c';
const DOWN = '#3a8e5a';
const pct = (p, d = 0) => (p == null ? 'n/a' : `${(p * 100).toFixed(d)}%`);
const TOGGLES = new Set(['is_male', 'uninsured', 'language_barrier', 'shift_work', 'smoker_current', 'diabetes', 'never_screened', 'family_history_any']);
const fmtAttr = (feature, v) => (v == null ? 'n/a' : TOGGLES.has(feature) ? (v ? 'yes' : 'no') : Number.isInteger(+v) ? `${v}` : (+v).toFixed(1));
const md = { p: (p) => <p {...p} />, strong: (p) => <strong style={{ color: 'var(--brand)', fontWeight: 700 }} {...p} /> };

function arc(cx, cy, r, a0, a1) {
  const p = (a) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  const [x0, y0] = p(a0); const [x1, y1] = p(a1);
  return `M ${x0} ${y0} A ${r} ${r} 0 ${a1 - a0 > Math.PI ? 1 : 0} 1 ${x1} ${y1}`;
}
function Gauge({ base, sim, changed }) {
  const W = 260, H = 150, cx = 130, cy = 132, R = 106;
  const ang = (p) => Math.PI + Math.PI * Math.min(Math.max(p, 0), 1);
  const stops = [[0, 0.3, BAND_COLOR.Low], [0.3, 0.5, BAND_COLOR.Moderate], [0.5, 0.7, BAND_COLOR.High], [0.7, 1, BAND_COLOR['Very high']]];
  const cur = sim ?? base;
  const color = BAND_COLOR[cur?.band] || 'var(--brand)';
  return (
    <div className="relative flex flex-col items-center">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="overflow-visible">
        {stops.map(([a, b, c]) => <path key={a} d={arc(cx, cy, R + 12, ang(a) + 0.004, ang(b) - 0.004)} stroke={c} strokeOpacity="0.22" strokeWidth="3" fill="none" />)}
        <path d={arc(cx, cy, R, Math.PI, 2 * Math.PI)} stroke="rgba(15,23,42,0.08)" strokeWidth="14" fill="none" strokeLinecap="round" />
        {base && <path d={arc(cx, cy, R, Math.PI, Math.max(ang(base.probability), Math.PI + 0.02))} stroke="rgba(15,23,42,0.22)" strokeWidth="14" fill="none" strokeLinecap="round" />}
        {cur && <path d={arc(cx, cy, R, Math.PI, Math.max(ang(cur.probability), Math.PI + 0.02))} stroke={color} strokeWidth="14" fill="none" strokeLinecap="round"
          style={{ transition: 'all 0.45s cubic-bezier(.2,.8,.2,1)', filter: `drop-shadow(0 2px 6px ${color}55)` }} />}
        {base && changed && (() => { const a = ang(base.probability); return <circle cx={cx + R * Math.cos(a)} cy={cy + R * Math.sin(a)} r="4.5" fill="#fff" stroke="rgba(15,23,42,0.5)" strokeWidth="1.5" />; })()}
        <text x={cx - R - 2} y={cy + 16} fontSize="9" fill="var(--text-faint)" textAnchor="middle" fontWeight="700">0%</text>
        <text x={cx + R + 2} y={cy + 16} fontSize="9" fill="var(--text-faint)" textAnchor="middle" fontWeight="700">100%</text>
      </svg>
      <div className="absolute left-0 right-0 flex flex-col items-center" style={{ top: 66 }}>
        <div className="text-[9px] font-bold uppercase tracking-[0.14em]" style={{ color: 'var(--text-faint)' }}>{changed ? 'Simulated · not completing' : 'Chance of not completing'}</div>
        <div className="font-extrabold tracking-tight leading-none" style={{ fontSize: 40, color, fontFeatureSettings: '"tnum" 1', transition: 'color 0.3s' }}>{pct(cur?.probability)}</div>
        <div className="text-[11px] font-bold mt-1 flex items-center gap-1.5" style={{ color: 'var(--text-dim)' }}>
          {changed && <span style={{ textDecoration: 'line-through', opacity: 0.7 }}>{pct(base?.probability)}</span>}
          <span className="badge" style={{ background: `${color}18`, color, border: `1px solid ${color}44` }}>{cur?.band}</span>
        </div>
      </div>
    </div>
  );
}

export default function ScreeningModelPage() {
  const [profiles, setProfiles] = useState([]);
  const [pid, setPid] = useState(null);
  const [base, setBase] = useState(null);
  const [values, setValues] = useState({});
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [card, setCard] = useState(null);
  const [explain, setExplain] = useState({ text: '', mode: null, model: null, running: false, stale: false, error: null });
  const abortRef = useRef(null);
  const explainAbort = useRef(null);

  useEffect(() => {
    getCrcProfiles().then(({ profiles: ps }) => { setProfiles(ps || []); if (!pid && ps?.length) setPid((ps.find((p) => p.id === 'far_from_care') || ps[0]).id); }).catch((e) => setErr(e.message));
    getCrcModel().then(setCard).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!pid) return;
    setBase(null); setResult(null); setErr(null);
    setExplain({ text: '', mode: null, model: null, running: false, stale: false, error: null });
    getCrcProfile(pid).then((b) => { setBase(b); setValues(b.values || {}); }).catch((e) => setErr(e.message));
  }, [pid]);

  const levers = base?.levers || [];
  const overrides = useMemo(() => {
    if (!base) return {};
    const o = {};
    for (const l of levers) {
      const rv = base.values[l.key]; const v = values[l.key];
      if (v == null) continue;
      if (rv == null || (l.kind === 'toggle' ? !!v !== !!rv : Math.abs(+v - +rv) > 1e-9)) o[l.key] = v;
    }
    return o;
  }, [base, values, levers]);
  const changed = Object.keys(overrides).length > 0;

  useEffect(() => {
    if (!base) return undefined;
    abortRef.current?.abort();
    const ctrl = new AbortController(); abortRef.current = ctrl;
    setBusy(true);
    const t = setTimeout(() => {
      postCrcSimulate(pid, overrides, ctrl.signal).then((r) => { if (!ctrl.signal.aborted) { setResult(r); setBusy(false); } })
        .catch((e) => { if (e.name !== 'AbortError') { setErr(e.message); setBusy(false); } });
    }, 180);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [base, pid, overrides]);
  useEffect(() => { setExplain((x) => (x.text && !x.running ? { ...x, stale: true } : x)); }, [overrides]);

  const setLever = useCallback((k, v) => setValues((old) => ({ ...old, [k]: v })), []);
  const reset = () => { if (base) setValues(base.values); };
  const applyPreset = (id) => getCrcProfilePreset(pid, id).then(({ overrides: o }) => setValues({ ...(base?.values || {}), ...o })).catch(() => {});
  const runExplain = () => {
    explainAbort.current?.abort();
    const ctrl = new AbortController(); explainAbort.current = ctrl;
    setExplain({ text: '', mode: null, model: null, running: true, stale: false, error: null });
    streamCrcExplain({ profileId: pid, overrides }, (ev) => {
      if (ev.type === 'meta') setExplain((x) => ({ ...x, mode: ev.mode, model: ev.model }));
      else if (ev.type === 'token') setExplain((x) => ({ ...x, text: x.text + ev.text }));
      else if (ev.type === 'final') setExplain((x) => ({ ...x, text: ev.text || x.text, mode: ev.mode, model: ev.model || x.model, running: false, error: ev.error || null }));
    }, ctrl.signal).catch((e) => { if (e.name !== 'AbortError') setExplain((x) => ({ ...x, running: false, error: e.message })); });
  };

  const groups = useMemo(() => { const g = new Map(); for (const l of levers) { if (!g.has(l.group)) g.set(l.group, []); g.get(l.group).push(l); } return [...g.entries()]; }, [levers]);
  const attribution = useMemo(() => (result?.attribution || []).slice(0, 7).map((a) => ({
    ...a, pts: +(a.delta_probability * 100).toFixed(1),
    change: a.from !== a.to && a.from != null ? `${fmtAttr(a.feature, a.from)} → ${fmtAttr(a.feature, a.to)}` : 'via interactions',
  })), [result]);
  // One line per row, so rows never overlap when the panel is short; the value change rides on the bar label.
  const AttrTick = ({ x, y, payload }) => (
    <text x={x} y={y} dy="3.5" textAnchor="end" fontSize="10.5" fontWeight="700" fill="#1e293b">{payload.value}</text>
  );
  const attrLabel = (v, i) => `${v > 0 ? '+' : ''}${v}${attribution[i]?.change && attribution[i].change !== 'via interactions' ? ` · ${attribution[i].change}` : ''}`;

  const pr = base?.profile;
  const sim = result?.simulated; const b0 = result?.baseline || base?.risk;
  const outreach = result?.outreach_after || base?.outreach;
  const metrics = card?.card?.metrics;
  const fairLang = (card?.fairness || []).filter((f) => f.dimension === 'language');

  return (
    <div className="h-full p-3 overflow-hidden flex flex-col gap-2.5">
      <div className="flex items-end justify-between gap-x-4 gap-y-2 shrink-0 px-1 flex-wrap">
        <div className="min-w-0" style={{ flex: '1 1 460px' }}>
          <h1 className="text-[17px] font-extrabold tracking-tight leading-none" style={{ color: 'var(--text)' }}>
            Model: who will not act on an invitation
          </h1>
          <p className="text-[10.5px] mt-1" style={{ color: 'var(--text-dim)' }}>
            Pick a profile and move a factor; the deployed model re-scores it live. The band feeds exactly one rule, outreach intensity (NHA-CS-01 §8.3); eligibility and the test never depend on it. Profiles are anonymous archetypes drawn from the programme's population.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
          {profiles.map((p) => (
            <button key={p.id} className={`sim-chip ${p.id === pid ? 'active' : ''}`} onClick={() => setPid(p.id)} title={p.description}>
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: BAND_COLOR[p.band] }} />
              <span>{p.label}</span>
              <span className="font-normal" style={{ color: 'var(--text-faint)' }}>{pct(p.probability)}</span>
            </button>
          ))}
        </div>
      </div>

      {err && <div className="text-[12px] px-1" style={{ color: 'var(--red)' }}>Model page unavailable: {err}</div>}
      {!base && !err && <Spinner />}

      {base && pr && (
        <div className="flex-1 grid grid-cols-12 gap-2.5 min-h-0">
          <div className="col-span-3 min-h-0">
            <Panel title="Factors" pad={false}
              right={<div className="flex items-center gap-1"><button className="sim-chip" onClick={reset} disabled={!changed}>Reset</button>
                {(base.presets || []).map((p) => <button key={p.id} className="sim-chip" title={p.description} onClick={() => applyPreset(p.id)}>{p.label}</button>)}</div>}>
              <div className="h-full min-h-0 overflow-y-auto px-3.5 pb-3">
                <div className="py-2 border-b border-[rgba(15,23,42,0.06)]">
                  <div className="text-[12.5px] font-extrabold leading-tight" style={{ color: 'var(--text)' }}>{pr.label} <span className="text-[10px] font-normal" style={{ color: 'var(--text-faint)' }}>profile</span></div>
                  <div className="text-[10px] leading-snug" style={{ color: 'var(--text-dim)' }}>{pr.age} · {pr.sex} · {pr.emirate} · {pr.description}</div>
                  <div className="text-[9.5px] leading-snug mt-1" style={{ color: 'var(--text-faint)' }}>Rules say: <b style={{ color: 'var(--text-md)' }}>{pr.pathway_test}</b> ({pr.due_status.replace('_', ' ')}) · nearest {pr.nearest_facility}</div>
                </div>
                {groups.map(([g, ls]) => (
                  <div key={g}>
                    <div className="sim-group-title">{g}</div>
                    {ls.map((l) => <Lever key={l.key} l={l} value={values[l.key]} recordValue={base.values[l.key]} onChange={(v) => setLever(l.key, v)} />)}
                  </div>
                ))}
              </div>
            </Panel>
          </div>

          <div className="col-span-3 min-h-0">
            <Panel title="Model estimate" right={busy && <span className="text-[9.5px] font-bold" style={{ color: 'var(--text-faint)' }}>re-scoring…</span>}>
              <div className="h-full min-h-0 flex flex-col overflow-y-auto">
                <Gauge base={b0} sim={sim} changed={changed} />
                <div className="grid grid-cols-2 gap-1.5 mt-1">
                  <Stat label="Change" value={changed && result ? `${result.delta.absolute >= 0 ? '+' : '−'}${Math.abs(result.delta.absolute * 100).toFixed(0)} pts` : 'n/a'}
                    sub={changed && result ? `${result.delta.relative_pct >= 0 ? '+' : '−'}${Math.abs(result.delta.relative_pct).toFixed(0)}% relative` : 'move a lever'}
                    tone={changed && result ? (result.delta.absolute < 0 ? 'good' : 'bad') : null} />
                  <Stat label="Among the due" value={sim ? `${sim.percentile.toFixed(0)}th` : b0 ? `${b0.percentile.toFixed(0)}th` : 'n/a'}
                    sub={changed && b0 ? `was ${b0.percentile.toFixed(0)}th percentile` : 'percentile of predicted risk'} />
                  <Stat label="Band" value={sim ? sim.band : b0?.band || 'n/a'} sub={changed && b0 && sim && b0.band !== sim.band ? `was ${b0.band}` : 'drives outreach only'} color={BAND_COLOR[sim?.band || b0?.band]} />
                  <Stat label="Channel" value={outreach?.channel?.toUpperCase() || 'n/a'} sub={outreach?.navigator ? 'patient navigator' : 'automated'} />
                </div>
                {outreach && (
                  <div className="scr-path mt-2">
                    <div className="text-[9.5px] font-bold uppercase tracking-[0.14em] mb-1" style={{ color: 'var(--text-faint)' }}>What rule R11 prescribes · {outreach.rule}</div>
                    <div className="text-[11px] leading-relaxed" style={{ color: 'var(--text-md)' }}>{outreach.plan}</div>
                    {changed && result && result.outreach_before.band !== result.outreach_after.band && (
                      <div className="text-[10px] mt-1" style={{ color: 'var(--text-dim)' }}>Before the change: {result.outreach_before.plan}</div>
                    )}
                  </div>
                )}
                {metrics && (
                  <div className="mt-2 text-[10px] leading-relaxed" style={{ color: 'var(--text-dim)' }}>
                    <div className="text-[9.5px] font-bold uppercase tracking-[0.14em] mb-1" style={{ color: 'var(--text-faint)' }}>Model card · {card.card.name.replace(' (Cancer screening)', '')} v{card.card.version}</div>
                    <div className="grid grid-cols-3 gap-1.5">
                      <Stat label="AUC, held out" value={metrics.auc} sub={`naive rule ${metrics.naive_rule_auc}`} />
                      <Stat label="Event rate" value={pct(metrics.event_rate)} sub="not completed in 90 d" />
                      <Stat label="Trained on" value={metrics.train_rows.toLocaleString()} sub={`test ${metrics.test_rows.toLocaleString()}`} />
                    </div>
                    {fairLang.length > 0 && (
                      <div className="mt-1.5">
                        <div className="text-[9.5px] font-bold uppercase tracking-[0.14em] mb-0.5" style={{ color: 'var(--text-faint)' }}>Held-out AUC by language</div>
                        {fairLang.map((f) => (
                          <div key={f.group} className="flex items-center justify-between text-[10px] py-0.5 border-b border-[rgba(15,23,42,0.05)] last:border-0">
                            <span className="font-semibold" style={{ color: 'var(--text-md)' }}>{f.group} <span style={{ color: 'var(--text-faint)' }}>n={f.n}</span></span>
                            <span className="tabular-nums"><b>{f.auc}</b> · event {pct(f.event_rate)} · high band {pct(f.high_band_rate)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="text-[9.5px] mt-1" style={{ color: 'var(--text-faint)' }}>{card.card.framework}. {card.card.constraints?.split('.')[0]}.</div>
                  </div>
                )}
              </div>
            </Panel>
          </div>

          <div className="col-span-6 min-h-0 grid grid-rows-2 gap-2.5">
            <Panel title="What moved the estimate (probability points)">
              {changed && attribution.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={attribution} layout="vertical" margin={{ top: 4, right: 104, bottom: 0, left: 4 }} barCategoryGap={6}>
                    <XAxis type="number" tick={{ fontSize: 9.5, fill: '#94a3b8' }} axisLine={false} tickLine={false} tickFormatter={(v) => `${v > 0 ? '+' : ''}${v}`}
                      domain={[(min) => Math.min(Math.floor(min * 1.35), -1), (max) => Math.max(Math.ceil(max * 1.35), 1)]} />
                    <YAxis type="category" dataKey="label" width={170} tick={<AttrTick />} axisLine={false} tickLine={false} interval={0} />
                    <ReferenceLine x={0} stroke="rgba(15,23,42,0.25)" />
                    <Tooltip cursor={{ fill: 'rgba(15,23,42,0.03)' }} formatter={(v) => [`${v > 0 ? '+' : ''}${v} pts`, 'contribution to the change']} contentStyle={{ fontSize: 11, borderRadius: 10, border: '1px solid rgba(15,23,42,0.08)' }} />
                    <Bar dataKey="pts" radius={[4, 4, 4, 4]} isAnimationActive animationDuration={350}>
                      {attribution.map((a) => <Cell key={a.feature} fill={a.pts > 0 ? UP : DOWN} fillOpacity={0.85} />)}
                      <LabelList dataKey="pts" content={({ x, y, width, height, value, index }) => (
                        <text x={(x || 0) + Math.max(width || 0, 0) + 6} y={(y || 0) + (height || 0) / 2} dy="3.5" fontSize="10" fontWeight="700" fill="#475569">
                          {attrLabel(value, index)}
                        </text>
                      )} />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex flex-col justify-center gap-1.5 px-1">
                  <div className="text-[10px] font-bold uppercase tracking-[0.14em]" style={{ color: 'var(--text-faint)' }}>Baseline drivers of the profile</div>
                  {(base.drivers || []).slice(0, 6).map((d) => (
                    <div key={d.feature} className="flex items-center gap-2 text-[11px]">
                      <span className="w-[190px] truncate font-semibold" style={{ color: 'var(--text-md)' }}>{d.label}</span>
                      <span className="w-[54px] tabular-nums" style={{ color: 'var(--text-dim)' }}>{fmtAttr(d.feature, d.value)}</span>
                      <div className="flex-1 h-[6px] rounded-full overflow-hidden" style={{ background: 'rgba(15,23,42,0.06)' }}>
                        <div className="h-full rounded-full" style={{ width: `${Math.min(100, Math.abs(d.contribution) / Math.abs(base.drivers[0].contribution) * 100)}%`, background: d.contribution > 0 ? UP : DOWN, opacity: 0.85 }} />
                      </div>
                      <span className="w-[44px] text-right tabular-nums text-[10px] font-bold" style={{ color: d.contribution > 0 ? UP : DOWN }}>{d.contribution > 0 ? '+' : ''}{d.contribution.toFixed(2)}</span>
                    </div>
                  ))}
                  <div className="text-[9.5px] mt-1" style={{ color: 'var(--text-faint)' }}>SHAP-style contributions in log-odds; red pushes towards not completing. Move a lever to see what changes the estimate.</div>
                </div>
              )}
            </Panel>
            <Panel title="Explanation"
              right={<div className="flex items-center gap-1.5">
                {explain.mode && <span className="badge badge-blue">{explain.mode === 'live' ? 'live explanation' : 'deterministic narrative'}</span>}
                <button className={`sim-chip ${!explain.text || explain.stale ? 'active' : ''}`} onClick={runExplain} disabled={explain.running || !result}>
                  {explain.running ? 'Explaining…' : explain.text ? 'Explain again' : 'Explain the change'}
                </button>
              </div>}>
              <div className="h-full min-h-0 flex flex-col">
                <div className="flex-1 min-h-0 overflow-y-auto text-[12px] leading-relaxed sim-explain pr-1" style={{ color: 'var(--text-md)' }}>
                  {explain.text ? (
                    <div style={{ opacity: explain.stale ? 0.55 : 1, transition: 'opacity 0.2s' }}>
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={md}>{explain.text}</ReactMarkdown>
                      {explain.running && <span className="sim-cursor" />}
                    </div>
                  ) : explain.running ? (
                    <div className="flex items-center gap-2 text-[11px]" style={{ color: 'var(--text-dim)' }}><span className="sim-cursor" /> Reading the model output…</div>
                  ) : (
                    <div className="text-[11px]" style={{ color: 'var(--text-dim)' }}>
                      {changed ? 'Ask for an explanation of why the estimate moved. The language model is handed the before-and-after scores, the attribution and the outreach rule, and narrates them; it adds no numbers of its own.'
                        : 'Move a lever, then ask for the explanation. It is grounded in the model output on this page: the language model explains, the model predicts, the rule decides the outreach.'}
                    </div>
                  )}
                </div>
                <div className="flex items-center justify-between gap-2 pt-1.5 mt-1 border-t border-[rgba(15,23,42,0.06)] text-[9.5px]" style={{ color: 'var(--text-faint)' }}>
                  <span>{explain.stale ? 'Levers changed since this explanation.' : explain.error ? `Language model unavailable (${explain.error}); deterministic narrative shown.` : `screening_uptake v${base.model_version || '1.0.0'} · an association, not a causal effect · every what-if is logged to the audit trail`}</span>
                </div>
              </div>
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}
