import { useEffect, useMemo, useState } from 'react';
import { getCrcDecisionCases, getCrcRules, runCrcDecision } from '../services/api';
import { Panel, Spinner } from '../components/ui';

/* Cancer screening, the rules: the decision laid out the way SAS Intelligent Decisioning lays one out.
   Left, the decision flow (rule sets, one model node, branches). Middle, the selected node: its rules
   as IF … THEN over named variables, or the model node, or the variables. Right, a scoring test on a
   real record: the decision path, the output variables and the rule-fired analysis. */

const KIND = { start: 'Start', end: 'End', ruleset: 'Rule set', model: 'Model node' };
const STATUS = {
  fired: { label: 'fired', cls: 'badge-green' }, evaluated: { label: 'evaluated · no rule fired', cls: 'badge-blue' },
  scored: { label: 'scored', cls: 'badge-amber' }, deferred: { label: 'deferred', cls: 'badge-amber' },
  skipped: { label: 'skipped', cls: '' }, reached: { label: '', cls: '' },
};
const KW = /\b(IF|THEN|ELSE|AND|OR|NOT|IN|CASE|WHEN|END|EXIT|CONTAINS ANY|CONTAINS|IS NOT NULL|TRUE|FALSE|MIN|NEAREST|BAND|TEMPLATE|NAMES)\b/g;
function Code({ text }) {
  const parts = String(text).split(KW);
  return <span className="dcode">{parts.map((t, i) => (i % 2 ? <span key={i} className="kw">{t}</span> : t))}</span>;
}
const fmtVal = (v) => (v == null ? 'null' : Array.isArray(v) ? (v.length ? v.join(', ') : '[ ]') : typeof v === 'boolean' ? (v ? 'TRUE' : 'FALSE') : String(v));
const OUTPUT_ORDER = ['pathway_id', 'test', 'interval', 'urgency', 'where', 'facility', 'apcs_points', 'apcs_tier', 'model_consulted', 'uptake_p', 'outreach_band', 'outreach_channel', 'navigator', 'safety_net'];

export default function ScreeningRulesPage() {
  const [flow, setFlow] = useState(null);
  const [cases, setCases] = useState([]);
  const [caseId, setCaseId] = useState(null);
  const [run, setRun] = useState(null);
  const [sel, setSel] = useState('rs_window');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    getCrcRules().then((r) => setFlow(r.decision)).catch((e) => setErr(e.message));
    getCrcDecisionCases().then((r) => { setCases(r.cases || []); if (r.cases?.length) setCaseId(r.cases[0].id); }).catch(() => {});
  }, []);
  useEffect(() => {
    if (!caseId) return;
    setBusy(true);
    runCrcDecision(caseId).then((r) => { setRun(r); setBusy(false); }).catch((e) => { setErr(e.message); setBusy(false); });
  }, [caseId]);

  const nodes = flow?.nodes || [];
  const selected = nodes.find((n) => n.id === sel) || nodes[0];
  const state = (id) => run?.nodes?.[id];
  const onPath = (id) => !run || run.path.includes(id);
  const names = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n.name])), [nodes]);

  if (err) return <div className="p-8 text-[13px]" style={{ color: 'var(--red)' }}>Rules unavailable: {err}</div>;
  if (!flow) return <Spinner />;

  return (
    <div className="h-full p-3 overflow-hidden flex flex-col gap-2.5">
      <div className="flex items-end justify-between gap-x-4 gap-y-2 shrink-0 px-1 flex-wrap">
        <div className="min-w-0" style={{ flex: '1 1 460px' }}>
          <h1 className="text-[17px] font-extrabold tracking-tight leading-none" style={{ color: 'var(--text)' }}>
            Decision flow: {flow.id}
          </h1>
          <p className="text-[10.5px] mt-1" style={{ color: 'var(--text-dim)' }}>
            The business rules, built the way a SAS Intelligent Decisioning decision is built: rule sets of IF … THEN rules over named variables, one model node, branches, and a scoring test with rule-fired analysis. The app's rules engine runs this flow; on SAS Viya the same decision is authored in Intelligent Decisioning and published to SAS Micro Analytic Service.
          </p>
        </div>
        <div className="flex items-center gap-1.5 flex-wrap justify-end">
          <span className="badge badge-green">v{flow.version} · {flow.status}</span>
          <span className="badge badge-blue">{flow.rule_sets} rule sets · {flow.models} model node · {flow.rule_count} rules</span>
          <span className="badge badge-blue">{flow.variables.inputs.length} inputs → {flow.variables.outputs.length} outputs</span>
        </div>
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-12 gap-2.5">
        {/* ── the flow ── */}
        <div className="col-span-3 min-h-0">
          <Panel title="Decision flow" pad={false} right={run && <span className="text-[9.5px] font-bold" style={{ color: 'var(--text-faint)' }}>path highlighted</span>}>
            <div className="h-full overflow-y-auto px-2 pb-2">
              <div className="dflow">
                {nodes.map((n, i) => {
                  const st = state(n.id); const path = onPath(n.id);
                  const badge = st && STATUS[st.status];
                  return (
                    <div key={n.id}>
                      {i > 0 && <div className={`dconn ${path && onPath(nodes[i - 1].id) ? 'on-path' : ''}`} />}
                      <button type="button" className={`dnode kind-${n.kind} ${sel === n.id ? 'selected' : ''} ${run ? (path ? 'on-path' : 'off-path') : ''}`} onClick={() => setSel(n.id)}>
                        <div className="flex items-center justify-between gap-2">
                          <span className="dnode-kind">{KIND[n.kind]}</span>
                          {badge?.label && <span className={`badge ${badge.cls}`} style={badge.cls ? { fontSize: 8, padding: '1px 6px' } : { fontSize: 8, padding: '1px 6px', background: 'rgba(15,23,42,0.05)', color: 'var(--text-faint)', border: '1px solid var(--hairline)' }}>{badge.label}</span>}
                        </div>
                        <div className="dnode-name">{n.name}</div>
                        <div className="dnode-sub">{n.kind === 'ruleset' ? `${n.rules.length} rule${n.rules.length !== 1 ? 's' : ''}${n.sub ? ` · ${n.sub}` : ''}` : n.sub}</div>
                        {st?.note && st.status !== 'reached' && <div className="dnode-note">{st.note}</div>}
                      </button>
                      {n.branch && <div className="dbranch">↳ {n.branch}</div>}
                    </div>
                  );
                })}
              </div>
            </div>
          </Panel>
        </div>

        {/* ── the selected node ── */}
        <div className="col-span-5 min-h-0">
          <Panel title={selected.kind === 'ruleset' ? `Rule set · ${selected.name}` : selected.kind === 'model' ? `Model node · ${selected.name}` : selected.kind === 'start' ? 'Input variables' : 'Output variables'} pad={false}
            right={selected.kind === 'ruleset' && <span className="text-[9.5px] font-bold" style={{ color: 'var(--text-faint)' }}>rules evaluate in order; the first pathway rule that fires exits</span>}>
            <div className="h-full overflow-y-auto px-2 pb-2">
              {selected.kind === 'ruleset' && (
                <table className="data-table">
                  <thead><tr><th>Rule</th><th>IF</th><th>THEN</th><th>§</th></tr></thead>
                  <tbody>
                    {selected.rules.map((r) => {
                      const rs = state(selected.id)?.rules?.find((x) => x.id === r.id);
                      const fired = rs?.fired; const off = run && !onPath(selected.id);
                      return (
                        <tr key={r.id} style={fired ? { background: 'rgba(4,120,87,0.07)' } : off ? { opacity: 0.45 } : undefined}>
                          <td style={{ whiteSpace: 'normal', minWidth: 120 }}>
                            <div className="flex items-center gap-1.5"><b style={{ color: 'var(--brand-lo)' }}>{r.id}</b>
                              {rs && (fired ? <span className="badge badge-green" style={{ fontSize: 8, padding: '1px 6px' }}>fired</span>
                                : rs.evaluated ? <span className="badge" style={{ fontSize: 8, padding: '1px 6px', background: 'rgba(15,23,42,0.05)', color: 'var(--text-faint)', border: '1px solid var(--hairline)' }}>false</span> : null)}
                            </div>
                            <div className="text-[10.5px] font-bold leading-snug mt-0.5" style={{ color: 'var(--text)' }}>{r.name}</div>
                            {rs?.note && <div className="text-[9.5px] leading-snug mt-0.5" style={{ color: fired ? 'var(--green)' : 'var(--text-faint)' }}>{rs.note}</div>}
                          </td>
                          <td style={{ whiteSpace: 'normal', maxWidth: 220 }}><Code text={r.condition} /></td>
                          <td style={{ whiteSpace: 'normal', maxWidth: 300 }}><Code text={r.actions} /></td>
                          <td><span className="badge badge-blue" style={{ fontSize: 8.5, padding: '1px 6px', whiteSpace: 'nowrap' }}>{r.source.section}</span></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
              {selected.kind === 'model' && (
                <div className="p-2 flex flex-col gap-2.5">
                  <div className="scr-path">
                    <div className="text-[9.5px] font-bold uppercase tracking-[0.14em] mb-1" style={{ color: 'var(--text-faint)' }}>Model node · the only place a prediction enters the decision</div>
                    <div className="text-[12px] font-extrabold" style={{ color: 'var(--text)' }}>Screening_Uptake_v1 · XGBoost, monotonic constraints · AUC 0.76 held out</div>
                    <div className="text-[11px] mt-1 leading-relaxed" style={{ color: 'var(--text-md)' }}>
                      Output <b>uptake_p</b>: the probability that an invitation is not followed by a completed test within 90 days. Consumed by exactly one rule, R11 (outreach intensity). It cannot change pathway_id, test, interval or urgency, which are set before it runs.
                    </div>
                  </div>
                  {[['Inputs', 'age, is_male, bmi, distance_km, hospital_distance_km, missed_appointments_12m, gp_visits_12m, language_barrier, uninsured, shift_work, smoker_current, diabetes, never_screened, family_history_any, apcs_points'],
                    ['Output', 'uptake_p ∈ [0, 1] → outreach_band via BAND(uptake_p, 0.30, 0.50, 0.70)'],
                    ['Reached when', "pathway_id IN ('screen_now','family_high') AND urgency IN ('now','soon')"],
                    ['Skipped when', 'symptoms override (R1, §9.1), surveillance, up to date, outside the window'],
                    ['On SAS Viya', 'a Model Studio model registered in Model Manager, published to MAS and dropped into the flow as a model node'],
                  ].map(([k, v]) => <div key={k} className="dvar"><b>{k}</b><span className="dcode" style={{ textAlign: 'right' }}>{v}</span></div>)}
                  {run && (
                    <div className="text-[11px] mt-1" style={{ color: 'var(--text-md)' }}>
                      In this test: <b style={{ color: state('model_uptake')?.status === 'scored' ? 'var(--green)' : 'var(--amber)' }}>{state('model_uptake')?.status}</b> · {state('model_uptake')?.note}
                    </div>
                  )}
                </div>
              )}
              {(selected.kind === 'start' || selected.kind === 'end') && (
                <div className="p-2">
                  <div className="text-[10px] mb-1.5" style={{ color: 'var(--text-dim)' }}>
                    {selected.kind === 'start' ? 'What the decision reads from the record (and the screening check form).' : 'What the decision writes back: the pathway, the routing and the outreach plan.'}
                    {run && <> Values from the current test, <b>{run.person_id}</b>.</>}
                  </div>
                  {(selected.kind === 'start' ? flow.variables.inputs : OUTPUT_ORDER).map((k) => (
                    <div key={k} className="dvar"><b>{k}</b><span>{run ? fmtVal((selected.kind === 'start' ? run.inputs : run.outputs)[k]) : '—'}</span></div>
                  ))}
                </div>
              )}
            </div>
          </Panel>
        </div>

        {/* ── the scoring test ── */}
        <div className="col-span-4 min-h-0">
          <Panel title="Scoring test" right={busy && <span className="text-[9.5px] font-bold" style={{ color: 'var(--text-faint)' }}>running…</span>}>
            <div className="h-full min-h-0 overflow-y-auto pr-1 flex flex-col gap-2.5">
              <div className="flex flex-wrap gap-1.5">
                {cases.map((c) => (
                  <button key={c.id} className={`sim-chip ${caseId === c.id ? 'active' : ''}`} onClick={() => setCaseId(c.id)} title={`${c.id} · ${c.sub}`}>{c.label}</button>
                ))}
              </div>
              {run && (
                <>
                  <div>
                    <div className="text-[9.5px] font-bold uppercase tracking-[0.14em] mb-1" style={{ color: 'var(--text-faint)' }}>Decision path · {run.person_id}</div>
                    <div className="dpath">
                      {run.path.map((id, i) => (
                        <span key={id} className="contents">
                          {i > 0 && <span className="arr">→</span>}
                          <button type="button" className={`seg ${id === 'model_uptake' ? 'model' : ''} ${sel === id ? 'sel' : ''}`} onClick={() => setSel(id)}>{names[id]}</button>
                        </span>
                      ))}
                    </div>
                    <div className="text-[10px] mt-1.5" style={{ color: 'var(--text-dim)' }}>
                      {cases.find((c) => c.id === caseId)?.sub && <>{cases.find((c) => c.id === caseId).sub}. </>}
                      Decided by <b style={{ color: 'var(--brand)' }}>{run.decided_by}</b>; the model {run.outputs.model_consulted ? 'was scored and set the outreach only' : 'was not consulted'}.
                    </div>
                  </div>
                  <div>
                    <div className="text-[9.5px] font-bold uppercase tracking-[0.14em] mb-1" style={{ color: 'var(--text-faint)' }}>Output variables</div>
                    {OUTPUT_ORDER.map((k) => (
                      <div key={k} className="dvar"><b>{k}</b>
                        <span style={{ color: run.outputs[k] == null ? 'var(--text-faint)' : k === 'safety_net' && run.outputs[k] ? 'var(--red)' : 'var(--text)' , fontWeight: ['pathway_id', 'outreach_channel', 'urgency'].includes(k) ? 800 : 500, textAlign: 'right' }}>{fmtVal(run.outputs[k])}</span>
                      </div>
                    ))}
                  </div>
                  <div>
                    <div className="text-[9.5px] font-bold uppercase tracking-[0.14em] mb-1" style={{ color: 'var(--text-faint)' }}>Rule-fired analysis</div>
                    <table className="data-table">
                      <thead><tr><th>Rule set</th><th>Rule</th><th>Fired</th></tr></thead>
                      <tbody>
                        {run.rule_fired.map((r) => (
                          <tr key={r.rule} style={r.fired ? { background: 'rgba(4,120,87,0.07)' } : undefined}>
                            <td style={{ whiteSpace: 'normal' }}><span className="text-[10px]" style={{ color: 'var(--text-dim)' }}>{names[r.ruleset]}</span></td>
                            <td style={{ whiteSpace: 'normal' }}><b style={{ color: 'var(--brand-lo)' }}>{r.rule}</b> <span className="text-[10px]" style={{ color: 'var(--text-md)' }}>{r.name}</span></td>
                            <td>{r.fired ? <span className="badge badge-green" style={{ fontSize: 8.5, padding: '1px 6px' }}>yes</span> : <span className="text-[10px]" style={{ color: 'var(--text-faint)' }}>no</span>}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="text-[9.5px] leading-relaxed pt-1 border-t border-[rgba(15,23,42,0.07)]" style={{ color: 'var(--text-faint)' }}>
                    The same engine runs behind the screening check, the programme tables and the agent, so they can never disagree. In SAS Intelligent Decisioning this panel is the scoring test with rule-fired analysis and decision-path tracking.
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
