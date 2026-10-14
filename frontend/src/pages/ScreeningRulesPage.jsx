import { useEffect, useState } from 'react';
import { assessCrc, getCrcRules } from '../services/api';
import { Panel, Spinner } from '../components/ui';

/* Example 2, the rules: the deterministic policy the agent cannot overrule, as a catalogue, and a
   live trace of which rule decided for a chosen person. Nothing on this page involves a model. */

const KIND = {
  pathway: { label: 'pathway', cls: 'badge-blue' }, modifier: { label: 'modifier', cls: 'badge-blue' },
  routing: { label: 'routing', cls: 'badge-green' }, programme: { label: 'programme', cls: 'badge-amber' },
  guardrail: { label: 'guardrail', cls: 'badge-red' },
};
const STATUS = {
  decided: { label: 'decided', cls: 'badge-green' }, applied: { label: 'applied', cls: 'badge-blue' },
  overridden: { label: 'overridden', cls: 'badge-amber' }, 'not fired': { label: 'not fired', cls: '' }, 'not applied': { label: 'not applied', cls: '' },
};
// Two extra people beyond the screening check's four, so every pathway rule can be watched firing.
const EXTRA = [
  { id: 'hassan', label: 'Hassan, 82, never screened', sub: 'Ages 76 to 85: a shared decision',
    inputs: { age: 82, sex: 'male', height_cm: 170, weight_kg: 78, smoking: 'former', family_history: 'none', history: [], symptoms: [], last_screen: 'never', location: { area: 'Al Dhaid' } } },
  { id: 'noor', label: 'Noor, 52, FIT last spring', sub: 'Up to date: next test in 12 months',
    inputs: { age: 52, sex: 'female', height_cm: 162, weight_kg: 66, smoking: 'never', family_history: 'none', history: [], symptoms: [], last_screen: 'fit_1y', location: { area: 'Al Nuaimiya' } } },
  { id: 'omar', label: 'Omar, 49, polyps removed in 2023', sub: 'Surveillance: FIT is not enough',
    inputs: { age: 49, sex: 'male', height_cm: 178, weight_kg: 88, smoking: 'never', family_history: 'none', history: ['polyps'], symptoms: [], last_screen: 'colo_10y', location: { area: 'Al Nakheel' } } },
];

export default function ScreeningRulesPage() {
  const [cat, setCat] = useState(null);
  const [err, setErr] = useState(null);
  const [who, setWho] = useState(null);
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { getCrcRules().then(setCat).catch((e) => setErr(e.message)); }, []);
  const people = cat ? [...cat.examples, ...EXTRA] : [];
  useEffect(() => { if (people.length && !who) setWho(people[1].id); }, [people.length]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const p = people.find((x) => x.id === who);
    if (!p) return;
    setBusy(true);
    assessCrc({ ...p.inputs, youngest_relative_age: p.inputs.youngest_relative_age ?? null }).then((r) => { setRes(r); setBusy(false); }).catch(() => setBusy(false));
  }, [who]); // eslint-disable-line react-hooks/exhaustive-deps

  if (err) return <div className="p-8 text-[13px]" style={{ color: 'var(--red)' }}>Rules unavailable: {err}</div>;
  if (!cat) return <Spinner />;
  const decided = res?.decided_by;

  return (
    <div className="h-full p-3 overflow-hidden flex flex-col gap-2.5">
      <div className="flex items-end justify-between gap-4 shrink-0 px-1">
        <div>
          <h1 className="text-[17px] font-extrabold tracking-tight leading-none" style={{ color: 'var(--text)' }}>
            Rules: the deterministic policy the agent cannot overrule
          </h1>
          <p className="text-[10.5px] mt-1" style={{ color: 'var(--text-dim)' }}>
            Thirteen rules implement {cat.guide}, evaluated in order; the first pathway rule that fires decides, the rest annotate. The model is consulted in exactly one of them (R11), and only for outreach effort. Pick a person on the right to watch them fire.
          </p>
        </div>
        <span className="text-[10px]" style={{ color: 'var(--text-faint)' }}>{cat.rules.length} rules · 1 document · 0 model calls on this page</span>
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-12 gap-2.5">
        <div className="col-span-7 min-h-0">
          <Panel title="The catalogue" pad={false}>
            <div className="h-full overflow-y-auto px-2 pb-2">
              <table className="data-table">
                <thead><tr><th>Rule</th><th>When</th><th>Then</th><th>Source</th></tr></thead>
                <tbody>
                  {cat.rules.map((r) => (
                    <tr key={r.id} style={decided === r.id ? { background: 'rgba(4,120,87,0.07)' } : undefined}>
                      <td style={{ whiteSpace: 'normal', minWidth: 150 }}>
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <b style={{ color: 'var(--brand-lo)' }}>{r.id}</b>
                          <span className={`badge ${KIND[r.kind].cls}`} style={{ fontSize: 8.5, padding: '1px 6px' }}>{KIND[r.kind].label}</span>
                        </div>
                        <div className="text-[11px] font-bold leading-snug mt-0.5" style={{ color: 'var(--text)' }}>{r.name}</div>
                      </td>
                      <td style={{ whiteSpace: 'normal', maxWidth: 230 }}><span className="text-[10.5px] leading-snug" style={{ color: 'var(--text-md)' }}>{r.when}</span></td>
                      <td style={{ whiteSpace: 'normal', maxWidth: 300 }}><span className="text-[10.5px] leading-snug" style={{ color: 'var(--text-md)' }}>{r.then}</span></td>
                      <td><span className="badge badge-blue" style={{ fontSize: 8.5, padding: '1px 6px', whiteSpace: 'nowrap' }}>{r.source.doc} {r.source.section}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>

        <div className="col-span-5 min-h-0">
          <Panel title="Watch the rules decide" right={busy && <span className="text-[9.5px] font-bold" style={{ color: 'var(--text-faint)' }}>evaluating…</span>}>
            <div className="h-full min-h-0 overflow-y-auto pr-1 flex flex-col gap-2.5">
              <div className="flex flex-wrap gap-1.5">
                {people.map((p) => (
                  <button key={p.id} className={`sim-chip ${who === p.id ? 'active' : ''}`} onClick={() => setWho(p.id)} title={p.sub}>{p.label}</button>
                ))}
              </div>
              {res && (
                <>
                  <div className="scr-path">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`urgency-pill urg-${res.pathway.urgency}`}>{res.pathway.urgency === 'later' ? 'nothing to book' : res.pathway.urgency === 'now' ? 'due now' : res.pathway.urgency}</span>
                      <h3 className="text-[14px] font-extrabold leading-tight" style={{ color: 'var(--text)' }}>{res.pathway.title}</h3>
                    </div>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2 text-[11px]">
                      <div><span className="scr-k">The test</span>{res.pathway.test}</div>
                      <div><span className="scr-k">How often</span>{res.pathway.interval}</div>
                    </div>
                    <div className="text-[10px] mt-2" style={{ color: 'var(--text-dim)' }}>
                      APCS {res.score.points}/{res.score.max_points} · {res.score.tier_label} · decided by <b style={{ color: 'var(--brand)' }}>{res.decided_by}</b>
                      {res.facilities?.[0] && <> · routed to <b style={{ color: 'var(--text-md)' }}>{res.facilities[0].name}</b> ({res.facilities[0].km} km)</>}
                    </div>
                  </div>
                  <div>
                    <div className="text-[9.5px] font-bold uppercase tracking-[0.14em] mb-1" style={{ color: 'var(--text-faint)' }}>Rule trace, in evaluation order</div>
                    <div className="flex flex-col gap-1">
                      {res.rule_trace.map((r) => {
                        const st = STATUS[r.status] || STATUS['not fired'];
                        const dim = r.status === 'not fired' || r.status === 'not applied';
                        return (
                          <div key={r.id} className="fac-row" style={{ opacity: dim ? 0.55 : 1, borderColor: r.status === 'decided' ? 'var(--green-border)' : undefined, background: r.status === 'decided' ? 'var(--green-bg)' : undefined }}>
                            <div className="fac-rank" style={{ background: dim ? 'rgba(15,23,42,0.08)' : undefined, color: dim ? 'var(--text-dim)' : undefined }}>{r.id.replace('R', '')}</div>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-baseline gap-2 flex-wrap">
                                <b className="text-[11.5px]" style={{ color: 'var(--text)' }}>{r.name}</b>
                                <span className="text-[9.5px]" style={{ color: 'var(--text-faint)' }}>{r.source.doc} {r.source.section}</span>
                              </div>
                              <div className="text-[10.5px]" style={{ color: 'var(--text-md)' }}>{r.note}</div>
                            </div>
                            <span className={`badge ${st.cls}`} style={st.cls ? undefined : { background: 'rgba(15,23,42,0.05)', color: 'var(--text-faint)', border: '1px solid var(--hairline)' }}>{st.label}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                  <div className="text-[9.5px] leading-relaxed pt-1 border-t border-[rgba(15,23,42,0.07)]" style={{ color: 'var(--text-faint)' }}>
                    The same function runs behind the screening check, the programme tables and the agent, so they can never disagree. R11 to R13 are programme and guardrail rules: they shape outreach and generated messages after the pathway is decided.
                  </div>
                </>
              )}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
