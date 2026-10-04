import { useEffect, useMemo, useRef, useState } from 'react';
import { assessCrc, getCrcOptions } from '../services/api';
import { Panel, Spinner } from '../components/ui';
import ScreeningMap from '../components/ScreeningMap';
import ScreeningChat from '../components/ScreeningChat';

/* Example 2: bowel (colorectal) cancer screening check. A few facts in, three things out:
   a risk tier, the right test and when, and the nearest EHS place to do it. */

const TIER = {
  average: { label: 'Average risk', color: 'var(--green)', bg: 'var(--green-bg)' },
  moderate: { label: 'Moderately raised', color: '#b45309', bg: 'var(--amber-bg)' },
  high: { label: 'Higher risk', color: 'var(--red)', bg: 'var(--red-bg)' },
};
const URGENCY = {
  urgent: { label: 'Urgent', cls: 'urg-urgent' }, now: { label: 'Due now', cls: 'urg-now' },
  soon: { label: 'Book soon', cls: 'urg-soon' }, later: { label: 'Nothing to book yet', cls: 'urg-later' },
};

const DEFAULT = {
  age: 45, sex: 'female', height_cm: 165, weight_kg: 70, smoking: 'never', diabetes: false,
  family_history: 'none', youngest_relative_age: '', history: [], symptoms: [], symptom_duration: '',
  notes: { health: '', family: '', screening: '', symptoms: '', lifestyle: '', other: '' },
  last_screen: 'never', activity: 'some', diet: 'mixed', alcohol: 'none', location: { area: 'Al Majaz' },
};
const HINT_LABEL = { symptoms: 'Tick it', history: 'Tick it', family_history: 'Open the list', smoking: 'Set smoking', last_screen: 'Open the list', diabetes: 'Set to yes' };

function Field({ label, hint, children }) {
  return (
    <div className="scr-field">
      <div className="scr-label">{label}{hint && <span className="scr-hint"> {hint}</span>}</div>
      {children}
    </div>
  );
}
function Section({ n, title, sub, children }) {
  return (
    <section className="scr-section">
      <div className="scr-section-head"><span className="scr-section-n">{n}</span><div><div className="scr-section-title">{title}</div>{sub && <div className="scr-section-sub">{sub}</div>}</div></div>
      <div className="flex flex-col gap-2.5">{children}</div>
    </section>
  );
}
function Notes({ value, onChange, placeholder }) {
  return (
    <textarea className="scr-notes" rows={2} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
  );
}
function Chips({ value, options, onChange }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button key={o.id} type="button" className={`sim-chip ${value === o.id ? 'active' : ''}`} onClick={() => onChange(o.id)}>{o.label}</button>
      ))}
    </div>
  );
}
function Checks({ values, options, onToggle }) {
  return (
    <div className="flex flex-col gap-1">
      {options.map((o) => (
        <label key={o.id} className={`scr-check ${values.includes(o.id) ? 'on' : ''}`}>
          <input type="checkbox" checked={values.includes(o.id)} onChange={() => onToggle(o.id)} />
          <span>{o.label}</span>
        </label>
      ))}
    </div>
  );
}

export default function ScreeningPage() {
  const [opts, setOpts] = useState(null);
  const [form, setForm] = useState(DEFAULT);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [geoBusy, setGeoBusy] = useState(false);
  const timer = useRef(null);

  useEffect(() => { getCrcOptions().then(setOpts).catch((e) => setErr(e.message)); }, []);

  // Re-assess 350 ms after the last change; the result keeps updating as the form is filled.
  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      const body = { ...form, youngest_relative_age: form.youngest_relative_age === '' ? null : Number(form.youngest_relative_age) };
      if (!(body.age >= 18 && body.age <= 100)) return;
      setBusy(true);
      try { setResult(await assessCrc(body)); setErr(null); } catch (e) { setErr(e.message); }
      setBusy(false);
    }, 350);
    return () => clearTimeout(timer.current);
  }, [form]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setNote = (k, v) => setForm((f) => ({ ...f, notes: { ...f.notes, [k]: v } }));
  // A hint read off the notes: one click applies it to the form (or scrolls to the field).
  const applyHint = (h) => {
    if (h.field === 'symptoms' || h.field === 'history') { if (!form[h.field].includes(h.value)) toggle(h.field, h.value); return; }
    if (h.field === 'diabetes') { set('diabetes', true); return; }
    if (h.field === 'smoking') { set('smoking', 'current'); return; }
    document.getElementById(`scr-${h.field}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };
  const toggle = (k, id) => setForm((f) => ({ ...f, [k]: f[k].includes(id) ? f[k].filter((x) => x !== id) : [...f[k], id] }));
  const emirates = useMemo(() => [...new Set((opts?.areas || []).map((a) => a.emirate))], [opts]);
  const areaOf = (name) => opts?.areas.find((a) => a.area === name);
  const emirate = form.location.area ? areaOf(form.location.area)?.emirate : form.location.emirate;
  const areas = (opts?.areas || []).filter((a) => a.emirate === (emirate || emirates[0]));
  const useMyLocation = () => {
    if (!navigator.geolocation) return;
    setGeoBusy(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => { set('location', { lat: pos.coords.latitude, lon: pos.coords.longitude, label: 'Your location' }); setGeoBusy(false); },
      () => setGeoBusy(false), { timeout: 8000 });
  };
  const bmi = form.height_cm > 100 && form.weight_kg > 25 ? (form.weight_kg / (form.height_cm / 100) ** 2).toFixed(1) : null;

  if (err && !opts) return <div className="p-8 text-[13px]" style={{ color: 'var(--red)' }}>Example 2 unavailable: {err}</div>;
  if (!opts) return <Spinner />;

  const tier = result ? TIER[result.score.tier] : null;
  const urg = result ? URGENCY[result.pathway.urgency] : null;

  return (
    <div className="h-full p-3 overflow-hidden flex flex-col gap-2.5">
      <div className="flex items-end justify-between shrink-0 px-1 gap-4">
        <div>
          <h1 className="text-[17px] font-extrabold tracking-tight leading-none" style={{ color: 'var(--text)' }}>
            Example 2: bowel cancer screening check
          </h1>
          <p className="text-[10.5px] mt-1" style={{ color: 'var(--text-dim)' }}>
            Fill in what you know, add notes in your own words, and it tells you your risk tier, the right test and when, and the nearest EHS place to do it. The answer updates as you type; the assistant at the bottom right answers questions about it.
          </p>
        </div>
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-5 gap-2.5">
        {/* ── about you ── */}
        <div className="col-span-2 min-h-0">
          <Panel title="About you">
            <div className="h-full min-h-0 overflow-y-auto pr-1 flex flex-col gap-3">
              <Section n="1" title="You" sub="The basics the score is built on.">
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Age">
                    <input type="number" min="18" max="100" className="scr-input" value={form.age} onChange={(e) => set('age', Number(e.target.value))} />
                  </Field>
                  <Field label="Sex">
                    <Chips value={form.sex} onChange={(v) => set('sex', v)} options={[{ id: 'female', label: 'Female' }, { id: 'male', label: 'Male' }]} />
                  </Field>
                  <Field label="Height" hint="cm">
                    <input type="number" min="120" max="220" className="scr-input" value={form.height_cm} onChange={(e) => set('height_cm', Number(e.target.value))} />
                  </Field>
                  <Field label="Weight" hint={bmi ? `kg · BMI ${bmi}` : 'kg'}>
                    <input type="number" min="30" max="250" className="scr-input" value={form.weight_kg} onChange={(e) => set('weight_kg', Number(e.target.value))} />
                  </Field>
                </div>
              </Section>

              <Section n="2" title="Your health" sub="Smoking and diabetes count; anything else you want to mention goes in the box.">
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Smoking">
                    <div id="scr-smoking">
                      <Chips value={form.smoking} onChange={(v) => set('smoking', v)}
                        options={[{ id: 'never', label: 'Never' }, { id: 'former', label: 'Used to' }, { id: 'current', label: 'Yes' }]} />
                    </div>
                  </Field>
                  <Field label="Diabetes">
                    <Chips value={form.diabetes ? 'yes' : 'no'} onChange={(v) => set('diabetes', v === 'yes')} options={[{ id: 'no', label: 'No' }, { id: 'yes', label: 'Yes' }]} />
                  </Field>
                </div>
                <Field label="Your own bowel history" hint="tick any that apply">
                  <Checks values={form.history} options={opts.history} onToggle={(id) => toggle('history', id)} />
                </Field>
                <Notes value={form.notes.health} onChange={(v) => setNote('health', v)}
                  placeholder="Other conditions, medicines you take, operations… (optional)" />
              </Section>

              <Section n="3" title="Your family" sub="Bowel cancer in a parent, brother, sister or child changes when you start and which test.">
                <div id="scr-family_history">
                  <Field label="Bowel cancer in the family">
                    <select className="scr-input" value={form.family_history} onChange={(e) => set('family_history', e.target.value)}>
                      {opts.family_history.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                    </select>
                    {(form.family_history === 'one_under60' || form.family_history === 'two_plus') && (
                      <div className="mt-1.5 flex items-center gap-2">
                        <span className="text-[10.5px]" style={{ color: 'var(--text-dim)' }}>Youngest at diagnosis</span>
                        <input type="number" min="18" max="100" placeholder="age" className="scr-input w-20" value={form.youngest_relative_age}
                          onChange={(e) => set('youngest_relative_age', e.target.value)} />
                      </div>
                    )}
                  </Field>
                </div>
                <Notes value={form.notes.family} onChange={(v) => setNote('family', v)}
                  placeholder="Who, which cancer, roughly what age… (optional)" />
              </Section>

              <Section n="4" title="Screening so far" sub="Whether you are already up to date.">
                <div id="scr-last_screen">
                  <Field label="Last screening">
                    <select className="scr-input" value={form.last_screen} onChange={(e) => set('last_screen', e.target.value)}>
                      {opts.last_screen.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                    </select>
                  </Field>
                </div>
                <Notes value={form.notes.screening} onChange={(v) => setNote('screening', v)}
                  placeholder="Where and when, what the result was… (optional)" />
              </Section>

              <Section n="5" title="How you feel now" sub="These matter more than everything above. Tick what applies in the last few weeks.">
                <Checks values={form.symptoms} options={opts.red_flags} onToggle={(id) => toggle('symptoms', id)} />
                {form.symptoms.length > 0 && (
                  <Field label="For how long?">
                    <Chips value={form.symptom_duration} onChange={(v) => set('symptom_duration', v)}
                      options={[{ id: 'under_2w', label: 'Under 2 weeks' }, { id: '2_6w', label: '2 to 6 weeks' }, { id: 'over_6w', label: 'Over 6 weeks' }]} />
                  </Field>
                )}
                <Notes value={form.notes.symptoms} onChange={(v) => setNote('symptoms', v)}
                  placeholder="Describe it in your own words: what, since when, how often… (optional)" />
              </Section>

              <Section n="6" title="How you live" sub="These do not change the test, they change the advice.">
                <Field label="Exercise">
                  <Chips value={form.activity} onChange={(v) => set('activity', v)}
                    options={[{ id: 'low', label: 'Hardly any' }, { id: 'some', label: 'Some' }, { id: 'regular', label: '150 min a week or more' }]} />
                </Field>
                <Field label="Diet">
                  <Chips value={form.diet} onChange={(v) => set('diet', v)}
                    options={[{ id: 'mixed', label: 'Mixed' }, { id: 'high_processed', label: 'Processed or red meat most days' }, { id: 'high_fibre', label: 'Lots of fibre' }]} />
                </Field>
                <Field label="Alcohol">
                  <Chips value={form.alcohol} onChange={(v) => set('alcohol', v)}
                    options={[{ id: 'none', label: 'None' }, { id: 'moderate', label: 'Sometimes' }, { id: 'heavy', label: 'Most days' }]} />
                </Field>
                <Notes value={form.notes.lifestyle} onChange={(v) => setNote('lifestyle', v)}
                  placeholder="Anything about diet, work, sleep, stress… (optional)" />
              </Section>

              <Section n="7" title="Where you live" sub="For the nearest place to go.">
                <div className="grid grid-cols-2 gap-1.5">
                  <select className="scr-input" value={emirate || emirates[0]}
                    onChange={(e) => set('location', { area: opts.areas.find((a) => a.emirate === e.target.value)?.area })}>
                    {emirates.map((e) => <option key={e} value={e}>{e}</option>)}
                  </select>
                  <select className="scr-input" value={form.location.area || ''} onChange={(e) => set('location', { area: e.target.value })}>
                    {!form.location.area && <option value="">{form.location.label || 'Pick an area'}</option>}
                    {areas.map((a) => <option key={a.area} value={a.area}>{a.area}</option>)}
                  </select>
                </div>
                <button type="button" className="sim-chip self-start" onClick={useMyLocation} disabled={geoBusy}>
                  {geoBusy ? 'Finding you…' : form.location.lat != null ? '✓ Using your location' : 'Use my location instead'}
                </button>
                <Notes value={form.notes.other} onChange={(v) => setNote('other', v)}
                  placeholder="Anything else you want the assistant to know… (optional)" />
              </Section>
            </div>
          </Panel>
        </div>

        {/* ── result ── */}
        <div className="col-span-3 min-h-0">
          <Panel title="Your result" right={busy && <span className="text-[9.5px] font-bold" style={{ color: 'var(--text-faint)' }}>updating…</span>}>
            {!result ? <Spinner /> : (
              <div className="h-full min-h-0 overflow-y-auto pr-1 flex flex-col gap-2.5">
                {result.note_hints?.length > 0 && (
                  <div className="scr-hints">
                    <div className="text-[9.5px] font-bold uppercase tracking-[0.14em] mb-1" style={{ color: '#7c4a0a' }}>From what you wrote</div>
                    <div className="text-[10.5px] mb-1.5" style={{ color: '#7c4a0a' }}>The score only counts what is ticked. You mentioned things in the notes that are not ticked yet:</div>
                    {result.note_hints.map((h, i) => (
                      <div key={i} className="scr-hint">
                        <span>{h.text}</span>
                        <button type="button" className="sim-chip" onClick={() => applyHint(h)}>{HINT_LABEL[h.field] || 'Apply'}</button>
                      </div>
                    ))}
                  </div>
                )}
                {/* tier */}
                <div className="scr-tier" style={{ borderColor: tier.color }}>
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div>
                      <div className="text-[9.5px] font-bold uppercase tracking-[0.14em]" style={{ color: 'var(--text-faint)' }}>Risk tier · APCS score</div>
                      <div className="text-[22px] font-black leading-tight" style={{ color: tier.color }}>{tier.label}</div>
                    </div>
                    <div className="text-right">
                      <div className="scr-points">{result.score.points}<span>/{result.score.max_points}</span></div>
                      <div className="scr-bar">{Array.from({ length: result.score.max_points }).map((_, i) => (
                        <span key={i} className={i < result.score.points ? 'on' : ''} style={i < result.score.points ? { background: tier.color } : undefined} />
                      ))}</div>
                    </div>
                  </div>
                  <div className="text-[11px] mt-2 leading-relaxed" style={{ color: 'var(--text-md)' }}>
                    Of 100 people in this tier who have a screening colonoscopy, about <b>{Math.round(result.score.prevalence_pct)}</b> are found to have an advanced polyp or an early cancer. That is what the tier means; it is not a prediction about you.
                  </div>
                  <details className="mt-1.5">
                    <summary className="text-[10.5px] font-bold cursor-pointer" style={{ color: 'var(--brand)' }}>How the points add up</summary>
                    <div className="mt-1 grid grid-cols-1 gap-0.5">
                      {result.score.factors.map((f) => (
                        <div key={f.factor} className="flex justify-between text-[10.5px]" style={{ color: 'var(--text-dim)' }}>
                          <span>{f.factor}</span><b style={{ color: f.points ? tier.color : 'var(--text-faint)' }}>+{f.points}</b>
                        </div>
                      ))}
                    </div>
                  </details>
                </div>

                {/* pathway */}
                <div className="scr-path">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`urgency-pill ${urg.cls}`}>{urg.label}</span>
                    <h3 className="text-[15px] font-extrabold leading-tight" style={{ color: 'var(--text)' }}>{result.pathway.title}</h3>
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2 text-[11px]">
                    <div><span className="scr-k">The test</span>{result.pathway.test}</div>
                    <div><span className="scr-k">How often</span>{result.pathway.interval}</div>
                  </div>
                  <p className="text-[11px] mt-2 leading-relaxed" style={{ color: 'var(--text-md)' }}>{result.pathway.why}</p>
                  <ol className="scr-steps">
                    {result.pathway.next_steps.map((s, i) => <li key={i}>{s}</li>)}
                  </ol>
                </div>

                {/* where */}
                <div>
                  <div className="text-[9.5px] font-bold uppercase tracking-[0.14em] mb-1" style={{ color: 'var(--text-faint)' }}>
                    Where to go{result.location.label ? ` · from ${result.location.label}` : ''}
                  </div>
                  {result.location.outside_ehs_footprint && (
                    <div className="scr-note">You are outside the Northern Emirates, where EHS facilities are. These are the nearest EHS places; the health authority where you live (DHA in Dubai, SEHA in Abu Dhabi) offers the same screening closer to home.</div>
                  )}
                  {result.facilities.length ? (
                    <>
                      <div className="flex flex-col gap-1 mb-2">
                        {result.facilities.map((f, i) => (
                          <div key={f.facility_id} className={`fac-row ${i === 0 ? 'first' : ''}`}>
                            <div className="fac-rank">{i + 1}</div>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-baseline gap-2 flex-wrap">
                                <b className="text-[12px]" style={{ color: 'var(--text)' }}>{f.name}</b>
                                <span className="text-[10px]" style={{ color: 'var(--text-faint)' }}>{f.type} · {f.region}</span>
                              </div>
                              <div className="text-[10.5px]" style={{ color: 'var(--text-md)' }}>{f.role}</div>
                              <div className="text-[9.5px]" style={{ color: 'var(--text-faint)' }}>{f.services.join(' · ')}</div>
                            </div>
                            <div className="text-right shrink-0">
                              <div className="text-[14px] font-extrabold" style={{ color: 'var(--text)' }}>{f.km} km</div>
                              <div className="text-[9.5px]" style={{ color: 'var(--text-faint)' }}>about {f.minutes} min</div>
                            </div>
                          </div>
                        ))}
                      </div>
                      <ScreeningMap user={result.location} facilities={result.facilities} height={210} />
                      <div className="text-[9.5px] mt-1" style={{ color: 'var(--text-faint)' }}>Book through the EHS app or call centre, and bring your Emirates ID. Hospitals are shown as squares, health centres as circles.</div>
                    </>
                  ) : (
                    <div className="scr-note">Pick your area on the left, or use your location, to see the nearest places.</div>
                  )}
                </div>

                {/* advice */}
                <div>
                  <div className="text-[9.5px] font-bold uppercase tracking-[0.14em] mb-1" style={{ color: 'var(--text-faint)' }}>What you can change</div>
                  <div className="grid grid-cols-2 gap-1.5">
                    {result.advice.map((a) => (
                      <div key={a.title} className="scr-advice"><b>{a.title}</b><span>{a.text}</span></div>
                    ))}
                  </div>
                </div>

                <div className="text-[9.5px] leading-relaxed pt-1 border-t border-[rgba(15,23,42,0.07)]" style={{ color: 'var(--text-faint)' }}>
                  <b>Sources:</b> {result.sources.join('; ')}. <br />{result.disclaimer}
                </div>
              </div>
            )}
          </Panel>
        </div>
      </div>
      <ScreeningChat person={{ ...form, youngest_relative_age: form.youngest_relative_age === '' ? null : Number(form.youngest_relative_age) }} />
    </div>
  );
}
