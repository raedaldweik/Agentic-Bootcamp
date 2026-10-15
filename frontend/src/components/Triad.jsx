import { useCallback, useEffect, useState } from 'react';
import { decideQueue, getQueue } from '../services/api';

/* The composite-AI triad: each kind of AI does only its own job. Seven boxes, lit as the
   agents work through a question; the last two are the human checkpoint and what it approved. */
export const STAGES = [
  { n: 1, title: 'AI agent', product: 'SAS Retrieval Agent Manager', sub: 'Plans, picks tools, writes cited narratives', agents: ['basira_supervisor'] },
  { n: 2, title: 'Predictive ML', product: 'SAS Viya', sub: 'Finds the cohort, ranks deterioration risk', agents: ['cohort_agent', 'risk_agent', 'pophealth_agent'] },
  { n: 3, title: 'Business rules', product: 'SAS Intelligent Decisioning', sub: 'Eligibility, exclusions, HbA1c thresholds', agents: ['rules_agent'] },
  { n: 4, title: 'Knowledge store', product: 'SAS Retrieval Agent Manager', sub: 'Indexed guidelines. No passage, no claim.', agents: ['guideline_agent'] },
  { n: 5, title: 'Staged outreach plan', product: '', sub: 'Rule-validated, nothing sent', agents: ['action_agent'] },
  { n: 6, title: 'Human checkpoints', product: '', sub: 'Override with a reason code', queue: 'pending' },
  { n: 7, title: 'Approved list', product: '', sub: 'To the outreach channels', queue: 'approved' },
];
export const REASON_CODES = [
  ['clinical_judgement', 'Clinical judgement'], ['already_contacted', 'Already contacted'],
  ['data_quality', 'Data quality concern'], ['capacity', 'No capacity this week'], ['patient_preference', 'Patient preference'],
];

export function useQueue() {
  const [items, setItems] = useState([]);
  const refresh = useCallback(() => getQueue().then((r) => setItems(r.items || r || [])).catch(() => {}), []);
  useEffect(() => { refresh(); const t = setInterval(refresh, 20000); return () => clearInterval(t); }, [refresh]);
  return { items, refresh };
}

export function TriadRail({ activeAgents, doneAgents, queue, onOpenCheckpoints }) {
  const pending = queue.filter((q) => q.status === 'pending').length;
  const approved = queue.filter((q) => q.status === 'approved').length;
  return (
    <div className="glass-card p-3.5 shrink-0 triad">
      <p className="panel-title mb-0.5">The composite AI triad</p>
      <p className="text-[9.5px] mb-2.5" style={{ color: 'var(--text-faint)' }}>Each kind of AI does only its own job</p>
      <ol className="triad-list">
        {STAGES.map((st) => {
          const isActive = st.agents?.some((a) => activeAgents.has(a));
          const isDone = st.agents?.some((a) => doneAgents.has(a));
          const count = st.queue === 'pending' ? pending : st.queue === 'approved' ? approved : null;
          const lit = isActive || isDone || (count > 0);
          const clickable = !!st.queue;
          return (
            <li key={st.n} className={`triad-stage ${isActive ? 'active' : ''} ${lit ? 'lit' : ''} ${clickable ? 'clickable' : ''}`}
              onClick={clickable ? onOpenCheckpoints : undefined}>
              <span className="triad-n">{st.n}</span>
              <span className="triad-body">
                <span className="triad-title">{st.title}{st.product && <em>{st.product}</em>}</span>
                <span className="triad-sub">{st.sub}</span>
              </span>
              {count != null && <span className={`triad-count ${count ? '' : 'zero'}`}>{count}</span>}
              {isActive && <span className="triad-pulse" />}
            </li>
          );
        })}
      </ol>
      <p className="text-[9px] mt-2 leading-snug" style={{ color: 'var(--text-faint)' }}>
        Example 1 runs on the app's own copy of the registry, model and rules. The same loop built live on Viya is the Population Health Builder demo.
      </p>
    </div>
  );
}

/* Box 6 and 7: what the agents staged, what the human did with it. */
export function CheckpointsPanel({ queue, refresh, onClose }) {
  const [busy, setBusy] = useState(null);
  const [reason, setReason] = useState({});
  const pending = queue.filter((q) => q.status === 'pending');
  const decided = queue.filter((q) => q.status !== 'pending').slice(0, 12);
  const decide = async (id, decision) => {
    setBusy(id);
    try { await decideQueue(id, decision, 'clinician', decision === 'rejected' ? (reason[id] || 'clinical_judgement') : ''); await refresh(); }
    catch { /* the list refreshes on its own */ }
    setBusy(null);
  };
  return (
    <div className="checkpoints" role="dialog" aria-label="Human checkpoints">
      <div className="checkpoints-head">
        <div>
          <div className="scr-chat-title">6 · Human checkpoints</div>
          <div className="scr-chat-sub">Staged by the agents, decided by a person. Nothing goes out without a decision here.</div>
        </div>
        <button className="team-gate-close" style={{ position: 'static' }} onClick={onClose} aria-label="Close">×</button>
      </div>
      <div className="checkpoints-body">
        {pending.length === 0 && <div className="scr-note" style={{ background: 'var(--green-bg)', color: 'var(--green)', borderColor: 'var(--green-border)' }}>Nothing waiting. Ask the agent for an outreach plan and it will stage one here.</div>}
        {pending.map((q) => (
          <div key={q.id} className="cp-item">
            <div className="cp-top">
              <span className="cp-type">{(q.type || '').replace('_', ' ')}</span>
              <b>{q.title}</b>
              <span className="cp-meta">{q.patient_ids?.length ? `${q.patient_ids.length} patients · ` : ''}{q.drafted_by} · {q.id}</span>
            </div>
            <div className="cp-detail">{q.detail}</div>
            {q.citation && <div className="cp-cite">Guideline: {q.citation}</div>}
            <div className="cp-actions">
              <button className="btn-primary cp-btn" disabled={busy === q.id} onClick={() => decide(q.id, 'approved')}>Approve</button>
              <select className="scr-input cp-reason" value={reason[q.id] || 'clinical_judgement'} onChange={(e) => setReason({ ...reason, [q.id]: e.target.value })}>
                {REASON_CODES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <button className="btn-secondary cp-btn" disabled={busy === q.id} onClick={() => decide(q.id, 'rejected')}>Override</button>
            </div>
          </div>
        ))}
        {decided.length > 0 && (
          <>
            <div className="text-[9.5px] font-bold uppercase tracking-[0.14em] mt-3 mb-1" style={{ color: 'var(--text-faint)' }}>7 · Approved list and overrides</div>
            {decided.map((q) => (
              <div key={q.id} className={`cp-done ${q.status}`}>
                <span className={`urgency-pill ${q.status === 'approved' ? 'urg-later' : 'urg-urgent'}`}>{q.status === 'approved' ? 'Approved' : 'Overridden'}</span>
                <span className="flex-1 min-w-0 truncate"><b>{q.title}</b>{q.patient_ids?.length ? ` · ${q.patient_ids.length} patients` : ''}</span>
                <span className="cp-meta">{q.status === 'approved' ? 'to the outreach channels' : `reason: ${(q.reason_code || 'clinical_judgement').replace('_', ' ')}`} · {q.decided_by}</span>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
