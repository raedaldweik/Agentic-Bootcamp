import { useEffect, useRef, useState } from 'react';
import { decideQueue, getCrcAudit, getCrcQueue, getCrcScenarios, getCrcWorklist, streamCrcAgent } from '../services/api';
import ResponseCard from '../components/ResponseCard';
import SourceViewer from '../components/SourceViewer';
import DetailsPopup from '../components/DetailsPopup';
import { AgentChip } from '../components/ui';

/*
 * Cancer screening, the composite agent. Left: the navigator worklists the agent works from and the
 * roster of roles. Centre: the conversation, with the live trace while the agents work and the
 * answer card (reasoning, charts, citations, drafted actions, full trace). Right: the human
 * checkpoints, the approval queue and the audit trail. Nothing the agent drafts is sent until a
 * person approves it here.
 */

const WELCOME = { role: 'assistant', welcome: true,
  content: 'This agent runs the screening programme the way the session describes composite AI: the rules decide who is due and which test, the model decides how hard to reach out, retrieval supplies the policy, the language model writes the message, a validator checks it, and you approve it. Pick a scenario below, or click a person on the worklist.' };
const BAND_CLS = { Low: 'badge-green', Moderate: 'badge-amber', High: 'badge-red', 'Very high': 'badge-red' };
const TYPE_LABEL = { screening_invite: 'invitation', screening_batch: 'outreach batch', urgent_referral: 'urgent referral', colonoscopy_referral: 'colonoscopy referrals' };
const fmtTime = (iso) => { try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); } catch { return ''; } };

export default function ScreeningAgentPage() {
  const [messages, setMessages] = useState([WELCOME]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [liveSteps, setLiveSteps] = useState([]);
  const [scenarios, setScenarios] = useState([]);
  const [info, setInfo] = useState(null);
  const [worklistKind, setWorklistKind] = useState('batch');
  const [worklist, setWorklist] = useState([]);
  const [queue, setQueue] = useState([]);
  const [audit, setAudit] = useState([]);
  const [source, setSource] = useState(null);
  const [details, setDetails] = useState(null);
  const [deciding, setDeciding] = useState(null);
  const sessionId = useRef(`crc-${Date.now().toString(36)}`);
  const inputRef = useRef(null);
  const endRef = useRef(null);

  const refreshOversight = () => {
    getCrcQueue().then((r) => setQueue(r.items || [])).catch(() => {});
    getCrcAudit().then((r) => setAudit(r.entries || [])).catch(() => {});
  };
  useEffect(() => {
    getCrcScenarios().then((r) => { setScenarios(r.scenarios || []); setInfo(r); }).catch(() => setScenarios([]));
    refreshOversight();
  }, []);
  useEffect(() => {
    getCrcWorklist(worklistKind, 14, worklistKind === 'due').then((r) => setWorklist(r.items || [])).catch(() => setWorklist([]));
  }, [worklistKind]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, liveSteps, loading]);

  const send = async (text, scenarioId = null) => {
    const q = (text || input).trim();
    if (!q || loading) return;
    setInput('');
    setMessages((m) => [...m, { role: 'user', content: q }]);
    setLoading(true); setLiveSteps([]);
    try {
      let finalData = null;
      await streamCrcAgent({ message: q, sessionId: sessionId.current, scenarioId }, (ev) => {
        if (ev.type === 'step') setLiveSteps((prev) => [...prev, ev]);
        else if (ev.type === 'final') finalData = ev;
      });
      if (finalData) setMessages((m) => [...m, { role: 'assistant', data: finalData, query: q }]);
      else setMessages((m) => [...m, { role: 'assistant', error: 'The stream ended without an answer. Try again.' }]);
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', error: `Connection error: ${e.message}` }]);
    }
    setLoading(false); setLiveSteps([]);
    refreshOversight();
    inputRef.current?.focus();
  };
  const review = (p) => {
    if (worklistKind === 'fit_positive') return send('Which positive FIT results have no colonoscopy yet, and what should happen to them?', 's_fit_positive');
    if (worklistKind === 'urgent') return send(`${p.person_id} has reported symptoms in the app. What happens?`, 's_symptoms');
    return send(`Review ${p.person_id} end to end: the rules, the model and a drafted invitation.`, 's_person');
  };
  const decide = async (item, decision) => {
    setDeciding(item.id);
    try { await decideQueue(item.id, decision, 'duty nurse'); } catch { /* the queue refresh shows the truth */ }
    setDeciding(null);
    refreshOversight();
  };

  const liveVisible = liveSteps.filter((s) => s.status === 'done').slice(-6);
  const pending = queue.filter((i) => i.status === 'pending');
  const decided = queue.filter((i) => i.status !== 'pending').slice(0, 3);

  return (
    <div className="h-full flex gap-4 p-4 pt-3">
      {/* Left rail: the worklists the agent works from, and the roster */}
      <div className="w-[262px] shrink-0 flex flex-col gap-3 min-h-0">
        <div className="glass-card flex flex-col flex-1 min-h-0">
          <div className="p-3.5 border-b border-[rgba(15,23,42,0.07)]">
            <p className="panel-title">Navigator worklist</p>
            <div className="seg-track mt-2" style={{ padding: 2 }}>
              {[['batch', "Today's batch"], ['fit_positive', 'FIT +'], ['urgent', 'Symptoms']].map(([k, label]) => (
                <button key={k} onClick={() => setWorklistKind(k)} className={`seg-pill ${worklistKind === k ? 'active' : ''}`} style={{ fontSize: 10, padding: '4px 8px' }}>{label}</button>
              ))}
            </div>
            <p className="text-[9.5px] mt-1.5 leading-snug" style={{ color: 'var(--text-faint)' }}>
              {worklistKind === 'batch' ? 'Due, not invited this year, by clinical priority. Click one to run it end to end.'
                : worklistKind === 'fit_positive' ? 'Positive FIT, no colonoscopy recorded. The §6.3 safety net.'
                : 'Red-flag symptoms reported: rule R1, no model.'}
            </p>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {worklist.map((p) => (
              <button key={p.person_id} onClick={() => review(p)} disabled={loading}
                className="w-full text-left px-2.5 py-2 rounded-lg transition-all hover:bg-[rgba(43,83,120,0.05)] border border-transparent disabled:opacity-60">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11.5px] font-bold" style={{ color: 'var(--text)' }}>{p.person_id}</span>
                  {worklistKind === 'fit_positive'
                    ? <span className={`badge ${p.days_since_fit > 56 ? 'badge-red' : 'badge-amber'}`} style={{ fontSize: 8.5, padding: '1px 6px' }}>{p.days_since_fit} d</span>
                    : worklistKind === 'urgent'
                      ? <span className="badge badge-red" style={{ fontSize: 8.5, padding: '1px 6px' }}>urgent</span>
                      : p.uptake_band && <span className={`badge ${BAND_CLS[p.uptake_band]}`} style={{ fontSize: 8.5, padding: '1px 6px' }}>{p.uptake_band}</span>}
                </div>
                <div className="text-[9.5px] truncate" style={{ color: 'var(--text-dim)' }}>
                  {p.age} {p.sex === 'male' ? 'M' : 'F'} · {p.area} · {p.apcs_tier} APCS{worklistKind === 'batch' && p.uptake_risk != null ? ` · ${Math.round(p.uptake_risk * 100)}%` : ''}
                </div>
              </button>
            ))}
            {!worklist.length && <div className="text-[10.5px] p-2" style={{ color: 'var(--text-faint)' }}>Nothing on this list.</div>}
          </div>
        </div>
        <div className="glass-card p-3.5 shrink-0">
          <p className="panel-title mb-2.5">Agent system</p>
          <div className="flex flex-wrap gap-1.5">
            {['screening_supervisor', 'rules_agent', 'risk_agent', 'guideline_agent', 'action_agent', 'guardrail_agent'].map((a) => <AgentChip key={a} agent={a} />)}
          </div>
          <p className="text-[9.5px] mt-2 leading-snug" style={{ color: 'var(--text-faint)' }}>
            {info?.live_chat
              ? <>Live function-calling loop · <b style={{ color: 'var(--text-dim)' }}>7 tools</b> · rules and model stay deterministic</>
              : <>Direct tool runs on live data. Free-form chat needs Anthropic model credentials on the server</>}
          </p>
        </div>
      </div>

      {/* Centre: the conversation */}
      <div className="flex-1 glass-card flex flex-col relative min-w-0" style={{ boxShadow: 'var(--glass-shadow-lg)' }}>
        <img src="/sas-logo.png" alt="" className="chat-watermark" />
        <div className="flex items-center justify-between px-6 py-3 border-b border-[rgba(15,23,42,0.07)] relative z-[5]">
          <div className="flex items-center gap-2 min-w-0">
            <span className="w-[3px] h-4 rounded shrink-0" style={{ background: 'var(--brand-grad)' }} />
            <span className="text-sm font-bold truncate" style={{ color: 'var(--text)' }}>Composite screening agent</span>
          </div>
          <div className="flex items-center gap-1.5 flex-wrap justify-end">
            {[['rules', 'badge-blue'], ['ML model', 'badge-amber'], ['retrieval', 'badge-green'], ['language model', 'badge-blue'], ['validator', 'badge-red'], ['human approval', 'badge-green']].map(([l, c]) => (
              <span key={l} className={`badge ${c}`} style={{ fontSize: 8.5, padding: '1px 7px' }}>{l}</span>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5 relative z-[1]">
          {messages.map((msg, i) => (
            <div key={i} className={`flex gap-2.5 animate-fade-up ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
              {msg.role === 'user' ? (
                <div className="w-8 h-8 rounded-lg shrink-0 flex items-center justify-center text-[10px] font-bold"
                  style={{ background: 'rgba(43,83,120,0.12)', border: '1px solid rgba(43,83,120,0.28)', color: 'var(--brand-lo)' }}>You</div>
              ) : (
                <div className="w-8 h-8 rounded-lg shrink-0 flex items-center justify-center p-1"
                  style={{ background: 'rgba(255,255,255,0.92)', border: '1px solid rgba(15,23,42,0.10)', boxShadow: '0 1px 3px rgba(15,23,42,0.08)' }}>
                  <img src="/sas-logo.png" alt="" className="w-full h-full object-contain" />
                </div>
              )}
              <div className="max-w-[78%] min-w-0">
                {msg.role === 'user' ? (
                  <div className="msg-user-bubble px-4 py-3 text-[13px] leading-[1.75]" style={{ color: 'var(--text)' }}>{msg.content}</div>
                ) : msg.error ? (
                  <div className="msg-bot-bubble px-4 py-3 text-[13px]" style={{ color: 'var(--red)' }}>{msg.error}</div>
                ) : msg.welcome ? (
                  <div className="msg-bot-bubble px-4 py-3 text-[13px] leading-[1.75]" style={{ color: 'var(--text)' }}>{msg.content}</div>
                ) : (
                  <ResponseCard data={msg.data} onOpenSource={setSource} onOpenDetails={(d) => setDetails({ data: d, query: msg.query })} />
                )}
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex gap-2.5 animate-fade-up">
              <div className="w-8 h-8 rounded-lg shrink-0 flex items-center justify-center p-1"
                style={{ background: 'rgba(255,255,255,0.92)', border: '1px solid rgba(15,23,42,0.10)', boxShadow: '0 1px 3px rgba(15,23,42,0.08)' }}>
                <img src="/sas-logo.png" alt="" className="w-full h-full object-contain" />
              </div>
              <div className="msg-bot-bubble px-4 py-3 min-w-[240px]">
                {liveVisible.length > 0 && (
                  <div className="mb-2.5 space-y-1.5">
                    {liveVisible.map((s, i, arr) => (
                      <div key={i} className="flex items-center gap-2 text-[11.5px] animate-fade-up" style={{ color: i === arr.length - 1 ? 'var(--brand-lo)' : 'var(--text-dim)' }}>
                        <AgentChip agent={s.agent} />
                        <span className="truncate font-mono text-[10.5px]">{s.tool}</span>
                        <span className="truncate text-[10.5px] flex-1">{s.detail}</span>
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--green)" strokeWidth="3" className="shrink-0"><polyline points="20 6 9 17 4 12" /></svg>
                      </div>
                    ))}
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <div className="flex gap-1.5">
                    {[0, 1, 2].map((j) => <span key={j} className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--brand)', opacity: 0.3, animation: `pop 1.4s ease-in-out infinite ${j * 0.15}s` }} />)}
                  </div>
                  <span className="text-[10px]" style={{ color: 'var(--text-faint)' }}>
                    {liveSteps.filter((s) => s.status === 'done').length > 0 ? `${liveSteps.filter((s) => s.status === 'done').length} steps so far` : 'agents working…'}
                  </span>
                </div>
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <div className="px-5 pb-4 pt-1 relative z-[1]">
          {scenarios.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {scenarios.map((s) => (
                <button key={s.id} className="suggestion-chip" disabled={loading} onClick={() => send(s.question, s.id)}>
                  <span className="chip-tag">{s.tag}</span>{s.label}
                </button>
              ))}
            </div>
          )}
          <div className="flex items-center gap-1.5 px-2 py-1 rounded-xl border border-[rgba(15,23,42,0.10)] transition-all focus-within:border-[var(--brand-hi)] focus-within:shadow-[0_0_0_3px_rgba(43,83,120,0.10)]"
            style={{ background: 'var(--glass-strong)', backdropFilter: 'blur(12px)' }}>
            <textarea ref={inputRef} rows="1" value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder={info?.live_chat ? 'Ask the agent: who is due in Fujairah, why is this person high risk, draft an invitation for SC-…' : 'Free-form questions need model credentials on the server; the scenario chips run every layer live'}
              className="flex-1 bg-transparent border-none outline-none text-[13px] py-2 px-2 resize-none leading-relaxed"
              style={{ fontFamily: 'Manrope, sans-serif', color: 'var(--text)' }} />
            <button onClick={() => send()} className="w-8 h-8 rounded-lg flex items-center justify-center text-white shrink-0 hover:scale-105 transition-transform"
              style={{ background: 'var(--brand-grad)', boxShadow: '0 3px 12px rgba(43,83,120,0.30)' }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
            </button>
          </div>
        </div>
      </div>

      {/* Right rail: the human checkpoints */}
      <div className="w-[300px] shrink-0 flex flex-col gap-3 min-h-0">
        <div className="glass-card flex flex-col min-h-0" style={{ flex: '1.3 1 0' }}>
          <div className="p-3.5 border-b border-[rgba(15,23,42,0.07)] flex items-center justify-between">
            <p className="panel-title">Approval queue</p>
            <span className={`badge ${pending.length ? 'badge-amber' : 'badge-green'}`}>{pending.length} pending</span>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
            {pending.map((item) => (
              <div key={item.id} className="rounded-xl px-3 py-2.5" style={{ background: 'var(--amber-bg)', border: '1px solid rgba(180,83,9,0.25)' }}>
                <div className="flex items-center gap-1.5 flex-wrap mb-1">
                  <span className="badge badge-amber" style={{ fontSize: 8.5, padding: '1px 6px' }}>{TYPE_LABEL[item.type] || item.type}</span>
                  <span className="text-[9.5px] font-mono" style={{ color: 'var(--text-faint)' }}>{item.id}</span>
                </div>
                <div className="text-[11.5px] font-bold leading-snug" style={{ color: 'var(--text)' }}>{item.title}</div>
                <div className="text-[10px] leading-snug mt-1 max-h-[64px] overflow-hidden" style={{ color: 'var(--text-md)' }}>{item.detail}</div>
                {item.citation && <div className="text-[9px] mt-1" style={{ color: 'var(--text-faint)' }}>{item.citation}</div>}
                <div className="flex gap-1.5 mt-2">
                  <button className="btn-primary" style={{ padding: '5px 10px', fontSize: 10.5 }} disabled={deciding === item.id} onClick={() => decide(item, 'approved')}>Approve</button>
                  <button className="btn-secondary" style={{ padding: '5px 10px', fontSize: 10.5 }} disabled={deciding === item.id} onClick={() => decide(item, 'rejected')}>Reject</button>
                </div>
              </div>
            ))}
            {!pending.length && <div className="text-[10.5px] p-2 leading-snug" style={{ color: 'var(--text-faint)' }}>Nothing waiting. Run a scenario: every drafted message and referral lands here first, and nothing is sent until you approve it (NHA-CS-01 §9.3).</div>}
            {decided.map((item) => (
              <div key={item.id} className="rounded-xl px-3 py-2" style={{ background: 'rgba(255,255,255,0.45)', border: '1px solid var(--hairline)', opacity: 0.75 }}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10.5px] font-bold truncate" style={{ color: 'var(--text-md)' }}>{item.title}</span>
                  <span className={`badge ${item.status === 'approved' ? 'badge-green' : 'badge-red'}`} style={{ fontSize: 8.5, padding: '1px 6px' }}>{item.status}</span>
                </div>
                <div className="text-[9px]" style={{ color: 'var(--text-faint)' }}>{item.decided_by} · {fmtTime(item.decided_at)}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="glass-card flex flex-col min-h-0" style={{ flex: '1 1 0' }}>
          <div className="p-3.5 border-b border-[rgba(15,23,42,0.07)]"><p className="panel-title">Audit trail</p></div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {audit.slice(0, 14).map((e) => (
              <div key={e.id} className="px-2 py-1.5 rounded-lg border-b border-[rgba(15,23,42,0.05)] last:border-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[9.5px] font-bold font-mono" style={{ color: e.severity === 'warning' ? 'var(--amber)' : e.severity === 'action' ? 'var(--brand)' : 'var(--text-dim)' }}>{e.event_type}</span>
                  <span className="text-[9px]" style={{ color: 'var(--text-faint)' }}>{fmtTime(e.timestamp)}</span>
                </div>
                <div className="text-[10px] leading-snug" style={{ color: 'var(--text-md)' }}>{e.detail}</div>
              </div>
            ))}
            {!audit.length && <div className="text-[10.5px] p-2" style={{ color: 'var(--text-faint)' }}>Every rule outcome, model score, draft and decision is written here.</div>}
          </div>
        </div>
      </div>

      {source && <SourceViewer source={source} onClose={() => setSource(null)} />}
      {details && <DetailsPopup data={details.data} query={details.query} onClose={() => setDetails(null)} onOpenSource={setSource} />}
    </div>
  );
}
