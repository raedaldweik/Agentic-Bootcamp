import { useEffect, useMemo, useState } from 'react';
import { getCrcDashboard, getCrcMap } from '../services/api';
import DynamicChart from '../components/DynamicChart';
import MapCard from '../components/MapCard';
import { KpiStrip, Panel, Spinner } from '../components/ui';

/* Cancer screening, the programme: the screening population at programme level, the same shape as
   the population-health story's registry overview. Every number is the same query the agent runs. */

const KPI_META = [
  { icon: 'users', tone: 'sand' }, { icon: 'check', tone: 'green' }, { icon: 'alert', tone: 'red' },
  { icon: 'activity', tone: 'gold' }, { icon: 'gauge', tone: 'teal' }, { icon: 'droplet', tone: 'rose' },
];
const shortFacility = (name) => {
  const n = name.replace(' Health Centre', '').replace(' Hospital', '').trim();
  const w = n.split(' ');
  return w.length > 1 ? w.slice(0, 2).join(' ') : n;
};
const METRIC_SHORT = {
  pct_up_to_date: 'Up to date', overdue: 'Overdue', completion_pct: 'Completion', mean_uptake_risk_pct: 'Model risk',
  fit_positivity_pct: 'FIT +', median_wait_days: 'Wait',
};

export default function ScreeningProgrammePage({ onOpenAgent }) {
  const [filter, setFilter] = useState({});
  const [d, setD] = useState(null);
  const [m, setM] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [metric, setMetric] = useState('completion_pct');
  const [view, setView] = useState('emirates');

  useEffect(() => {
    let alive = true;
    setBusy(true);
    getCrcDashboard(filter).then((r) => { if (alive) { setD(r); setBusy(false); } })
      .catch((e) => { if (alive) { setErr(e.message); setBusy(false); } });
    return () => { alive = false; };
  }, [filter]);
  useEffect(() => { getCrcMap().then(setM).catch(() => {}); }, []);

  const toggle = (key, value) => setFilter((f) => {
    if (value == null || f[key] === value) { const { [key]: _drop, ...rest } = f; return rest; }
    return { ...f, [key]: value };
  });

  const bench = useMemo(() => (d ? d.facility_benchmark.map((f) => ({ facility: shortFacility(f.facility), full: f.facility, 'up to date': f.pct_up_to_date })) : []), [d]);
  const benchFull = useMemo(() => Object.fromEntries(bench.map((b) => [b.facility, b.full])), [bench]);
  const activeFac = filter.facility ? bench.find((b) => b.full === filter.facility)?.facility ?? null : null;
  const spec = useMemo(() => {
    if (!m) return null;
    const meta = m.metric_meta[metric];
    return { type: 'map', metric, metric_label: meta.label, worse_is_high: meta.worse_is_high, popup: m.popup,
      facilities: m.facilities.map((f) => ({ ...f, value: f[metric] })),
      highlight: m.facilities.filter((f) => f.status === 'flagged').map((f) => f.name) };
  }, [m, metric]);
  const selectedFacId = filter.facility && m ? m.facilities.find((f) => f.name === filter.facility)?.facility_id : null;

  if (err) return <div className="p-8 text-[13px]" style={{ color: 'var(--red)' }}>Programme dashboard unavailable: {err}</div>;
  if (!d) return <Spinner />;
  const chips = d.filter.chips || [];
  const filtered = chips.length > 0;

  return (
    <div className="h-full p-3 overflow-hidden flex flex-col gap-2.5" style={{ opacity: busy ? 0.75 : 1, transition: 'opacity 0.2s' }}>
      <div className="flex items-end justify-between gap-x-4 gap-y-2 shrink-0 px-1 flex-wrap">
        <div className="min-w-0" style={{ flex: '1 1 420px' }}>
          <h1 className="text-[17px] font-extrabold tracking-tight leading-none" style={{ color: 'var(--text)' }}>
            Programme overview: colorectal cancer screening
          </h1>
          <p className="text-[10.5px] mt-1" style={{ color: 'var(--text-dim)' }}>
            Residents aged 40 to 75 of the Northern Emirates, their screening status under the rules, and what the programme's invitations achieved. Every figure is the same query the example agent runs.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
          <button type="button" className="badge badge-red" style={{ cursor: 'pointer' }} onClick={onOpenAgent} title="Open the example agent">
            {d.fit_positive_no_colonoscopy} positive FITs without colonoscopy
          </button>
          <button type="button" className="badge badge-amber" style={{ cursor: 'pointer' }} onClick={onOpenAgent} title="Open the example agent">
            {d.urgent_symptoms} with red-flag symptoms
          </button>
          <div className="filter-bar">
            {chips.map((c) => (
              <span key={c.key} className="filter-chip">
                <span className="k">{c.label}</span><span>{c.value}</span>
                <button type="button" aria-label={`Remove ${c.label} filter`} onClick={() => toggle(c.key, null)}>×</button>
              </span>
            ))}
            {filtered ? (
              <>
                <span className="filter-hint"><b style={{ color: 'var(--text-md)' }}>{d.filter.patients.toLocaleString()}</b> of {d.filter.total.toLocaleString()} people</span>
                <button type="button" className="filter-clear" onClick={() => setFilter({})}>Clear</button>
              </>
            ) : <span className="filter-hint">Click a bar or a facility to filter every panel</span>}
          </div>
        </div>
      </div>

      <KpiStrip items={d.kpis.map((k, i) => ({ ...k, ...KPI_META[i] }))} />

      <div className="flex-1 grid grid-cols-12 grid-rows-2 gap-2.5 min-h-0">
        <div className="col-span-5">
          <Panel title={filtered ? 'Invitations and 90-day completions, 36 months (filtered people)' : 'Invitations sent and completed within 90 days, 36 months'}>
            <DynamicChart bare spec={{
              type: 'line', xKey: 'month', data: d.trend,
              yKeys: [{ key: 'Invited', label: 'Invited' }, { key: 'Completed within 90 days', label: 'Completed within 90 days' }],
            }} />
          </Panel>
        </div>
        <div className="col-span-3">
          <Panel title="Predicted non-completion among the due (model)">
            <DynamicChart bare spec={{
              type: 'bar', xKey: 'band', data: d.uptake_bands.map((b) => ({ band: b.band, people: b.people })),
              yKeys: [{ key: 'people', label: 'People' }],
            }} onSelect={(label) => toggle('band', label)} activeLabel={filter.band || null} />
          </Panel>
        </div>
        <div className="col-span-4 row-span-2">
          <Panel title="Facility map" pad={false}
            right={
              <div className="flex items-center gap-2 flex-wrap justify-end">
                <div className="seg-track" style={{ padding: 2 }}>
                  {[['emirates', 'Emirates'], ['sharjah', 'Sharjah']].map(([k, label]) => (
                    <button key={k} onClick={() => setView(k)} className={`seg-pill ${view === k ? 'active' : ''}`} style={{ fontSize: 10, padding: '4px 9px' }}>{label}</button>
                  ))}
                </div>
                {m && (
                  <div className="seg-track" style={{ padding: 2 }}>
                    {Object.keys(m.metrics).slice(0, 4).map((k) => (
                      <button key={k} onClick={() => setMetric(k)} className={`seg-pill ${metric === k ? 'active' : ''}`} style={{ fontSize: 10, padding: '4px 9px' }}>{METRIC_SHORT[k] || k}</button>
                    ))}
                  </div>
                )}
              </div>
            }>
            <div className="h-full px-2 pb-2">
              {spec ? <MapCard spec={spec} height="100%" compact view={view} selectedId={selectedFacId}
                onSelect={(fid) => { const f = m.facilities.find((x) => x.facility_id === fid); if (f) toggle('facility', f.name); }} /> : <Spinner />}
            </div>
          </Panel>
        </div>

        <div className="col-span-3">
          <Panel title="Facility benchmark: % of the eligible up to date">
            <DynamicChart bare spec={{ type: 'bar', xKey: 'facility', data: bench, yKeys: [{ key: 'up to date', label: '% up to date' }] }}
              onSelect={(label) => toggle('facility', benchFull[label] || null)} activeLabel={activeFac} />
          </Panel>
        </div>
        <div className="col-span-2">
          <Panel title="90-day completion by nationality group">
            <DynamicChart bare spec={{
              type: 'bar', xKey: 'group', data: d.equity.map((e) => ({ group: e.group.replace(' / other', ''), 'completion %': e.completion_pct })),
              yKeys: [{ key: 'completion %', label: 'Completion %' }],
            }} onSelect={(label) => { const e = d.equity.find((x) => x.group.replace(' / other', '') === label); toggle('nationality', e ? e.group : null); }}
              activeLabel={filter.nationality ? filter.nationality.replace(' / other', '') : null} />
          </Panel>
        </div>
        <div className="col-span-3">
          <Panel title="From invitation to finding, 36 months">
            <div className="h-full overflow-y-auto px-1">
              {d.funnel.map((f, i) => (
                <div key={f.stage} className="flex items-center justify-between py-1.5 px-1 border-b border-[rgba(15,23,42,0.05)] last:border-0">
                  <span className="text-[10px] font-semibold leading-tight pr-1" style={{ color: 'var(--text-md)' }}>
                    {f.stage}
                  </span>
                  <span className="text-[10.5px] font-extrabold shrink-0" style={{ color: i === d.funnel.length - 1 ? 'var(--red)' : 'var(--text)' }}>
                    {f.n.toLocaleString()}
                  </span>
                </div>
              ))}
              <div className="text-[9.5px] mt-1.5 leading-snug" style={{ color: 'var(--text-faint)' }}>
                Positive FIT to colonoscopy: median {d.colonoscopy_wait.median_days ?? 'n/a'} days · {d.colonoscopy_wait.within_8_weeks_pct}% within the 8-week standard (NHA-CS-01 §6.2)
              </div>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
