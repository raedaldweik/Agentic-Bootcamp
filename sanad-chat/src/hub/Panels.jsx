// The side panels: the notebook (what has been raised and saved), the details of one
// answer (every step, tool call and model call), a source passage, and the access gate.
import { useEffect, useState } from 'react';
import Icon from './Icon';
import { niceTime } from './Menus';
import { getTrace, unlock } from '../lib/hubApi';

function Sheet({ title, icon, onClose, children, width = 460, foot }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="hub-sheet-backdrop" onClick={onClose}>
      <aside className="hub-sheet animate-sheet" style={{ width }} onClick={(e) => e.stopPropagation()} role="dialog" aria-label={title}>
        <header className="hub-sheet-head">
          <Icon name={icon} size={17} style={{ color: 'var(--brand-hi)' }} />
          <h2>{title}</h2>
          <button className="hub-icon-btn ms-auto" onClick={onClose} title="Close"><Icon name="close" size={16} /></button>
        </header>
        <div className="hub-sheet-body">{children}</div>
        {foot && <footer className="hub-sheet-foot">{foot}</footer>}
      </aside>
    </div>
  );
}

const KIND_ICON = { tool_request: 'wrench', finding_draft: 'clipboard', deviation_package: 'shield', recovery_submission: 'route',
  step_confirmation: 'check', note: 'doc', answer: 'bookmark' };

const label = (k) => k.replace(/_ts$/, '').replace(/_usd$/, ' (USD)').replace(/_mm$/, ' (mm)').replace(/_/g, ' ');
const TIME = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;

function Value({ v }) {
  if (v == null || v === '') return <span style={{ color: 'var(--text-faint)' }}>none</span>;
  if (typeof v === 'string' && TIME.test(v)) return <span>{niceTime(v)}</span>;
  if (Array.isArray(v)) {
    return <span>{v.map((x, i) => <span key={i} className="block">{typeof x === 'object' ? Object.entries(x).filter(([, y]) => y !== '' && y != null).map(([k, y]) => `${label(k)}: ${y}`).join(' · ') : String(x)}</span>)}</span>;
  }
  if (typeof v === 'object') return <span>{Object.entries(v).filter(([, y]) => y != null).map(([k, y]) => `${label(k)}: ${typeof y === 'object' ? JSON.stringify(y) : (TIME.test(String(y)) ? niceTime(y) : y)}`).join(' · ')}</span>;
  return <span>{String(v)}</span>;
}

export function Notebook({ items, onClose, onRemove, onReset }) {
  const [open, setOpen] = useState(null);
  const [confirming, setConfirming] = useState(false);
  return (
    <Sheet title={`Notebook${items.length ? ` (${items.length})` : ''}`} icon="book" onClose={onClose}
      foot={(
        <div className="flex items-center gap-3">
          <span className="flex-1">Requests and drafts here are pending. An authorised person decides each one.</span>
          {confirming
            ? <><button className="hub-btn is-danger" onClick={() => { setConfirming(false); onReset(); }}>Clear everything</button>
                <button className="hub-btn" onClick={() => setConfirming(false)}>Keep</button></>
            : <button className="hub-btn" onClick={() => setConfirming(true)} title="Forget this browser's conversations and notebook">Clear my history</button>}
        </div>
      )}>
      {items.length === 0 && (
        <div className="hub-empty">
          <Icon name="book" size={26} />
          <p>Nothing here yet.</p>
          <span>Requests you raise, drafts you record and answers you save are kept here.</span>
        </div>
      )}
      {items.map((r) => (
        <div key={r.id} className="hub-record">
          <button className="hub-record-head" onClick={() => setOpen(open === r.id ? null : r.id)}>
            <span className="hub-record-icon"><Icon name={KIND_ICON[r.kind] || 'doc'} size={15} /></span>
            <span className="min-w-0 flex-1 text-start">
              <span className="hub-record-title">{r.title}</span>
              <span className="hub-record-meta">{r.id} · {r.label} · {r.by} · shop time {niceTime(r.shop_time)}</span>
            </span>
            <Icon name="chevron" size={14} className={`transition-transform ${open === r.id ? 'rotate-180' : ''}`} />
          </button>
          <div className={`hub-record-status ${/^(pending|draft|routed|submitted)/i.test(r.status) ? 'is-pending' : ''}`}>{r.status}</div>
          {open === r.id && (
            <div className="hub-record-detail">
              {Object.entries(r.detail || {}).filter(([k, v]) => v != null && v !== '' && k !== 'queryId').map(([k, v]) => (
                <div key={k} className="hub-kv-row"><span className="hub-kv-label">{label(k)}</span><span className="hub-kv-value"><Value v={v} /></span></div>
              ))}
              <button className="hub-btn is-quiet mt-2" onClick={() => onRemove(r.id)}><Icon name="trash" size={13} /> Remove from notebook</button>
            </div>
          )}
        </div>
      ))}
    </Sheet>
  );
}

const ms = (v) => (v == null ? '' : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`);

export function Details({ turn, onClose }) {
  const [trace, setTrace] = useState(null);
  useEffect(() => { getTrace(turn.queryId).then(setTrace).catch(() => setTrace({})); }, [turn.queryId]);
  const u = turn.usage || {};
  const calls = trace?.toolCalls || [];
  const llm = trace?.llmCalls || [];
  const docs = trace?.retrievalCalls || [];
  return (
    <Sheet title="How this answer was produced" icon="grid" onClose={onClose} width={560}>
      <div className="hub-detail-question">{turn.content}</div>
      <div className="hub-stats">
        <div><b>{ms(turn.timing?.total_ms)}</b><span>Total time</span></div>
        <div><b>{turn.timing?.first_text_ms != null ? ms(turn.timing.first_text_ms) : 'n/a'}</b><span>First words</span></div>
        <div><b>{u.model_calls ?? 0}</b><span>Model calls</span></div>
        <div><b>{calls.length}</b><span>Data lookups</span></div>
      </div>
      <div className="hub-kv mb-3">
        <div className="hub-kv-row"><span className="hub-kv-label">Asked by</span><span className="hub-kv-value">{turn.personaTitle} {turn.personaId}</span></div>
        <div className="hub-kv-row"><span className="hub-kv-label">Shop time</span><span className="hub-kv-value">{turn.shopTimeNice}</span></div>
        <div className="hub-kv-row"><span className="hub-kv-label">Answered by</span><span className="hub-kv-value">{turn.model ? `Language model (${turn.model})` : 'Shop data directly, no language model'}</span></div>
        {u.input_tokens != null && turn.model && (
          <div className="hub-kv-row"><span className="hub-kv-label">Tokens</span>
            <span className="hub-kv-value">{(u.input_tokens + (u.cache_read_input_tokens || 0) + (u.cache_creation_input_tokens || 0)).toLocaleString()} in ({(u.cache_read_input_tokens || 0).toLocaleString()} from cache) · {u.output_tokens.toLocaleString()} out</span></div>
        )}
      </div>

      <h4 className="hub-block-title">Steps</h4>
      <ol className="hub-timeline mb-4">
        {(turn.steps || []).map((s) => (
          <li key={s.id} className={`state-${s.state === 'error' ? 'bad' : 'good'}`}>
            <span className="hub-timeline-dot" />
            <div className="hub-timeline-label">{s.label}{s.detail ? ` · ${s.detail}` : ''} <span className="hub-menu-item-id">{ms(s.ms)}</span></div>
            {s.note && <div className="hub-timeline-sub">{s.note}</div>}
          </li>
        ))}
      </ol>

      {trace == null && <div className="hub-empty"><span>Loading the trace…</span></div>}
      {calls.length > 0 && <h4 className="hub-block-title">Data lookups and actions</h4>}
      {calls.map((c, i) => (
        <details key={i} className="hub-trace">
          <summary>
            <Icon name={c.ok ? 'check' : 'x'} size={14} style={{ color: c.ok ? 'var(--green)' : 'var(--red)' }} />
            <code>{c.name}</code>
            {c.prefetched && <span className="hub-pill tone-info">fetched ahead</span>}
            <span className="ms-auto hub-menu-item-id">{ms(c.ms)}</span>
          </summary>
          <div className="hub-trace-body">
            <div className="hub-trace-label">Input</div>
            <pre>{JSON.stringify(c.input, null, 2)}</pre>
            <div className="hub-trace-label">Result</div>
            <pre>{JSON.stringify(c.output, null, 2)}</pre>
          </div>
        </details>
      ))}
      {llm.length > 0 && <h4 className="hub-block-title mt-4">Model calls</h4>}
      {llm.map((c, i) => (
        <div key={i} className="hub-trace is-flat">
          <Icon name="bolt" size={14} style={{ color: 'var(--brand-hi)' }} />
          <code>{c.model}</code>
          <span className="hub-menu-item-id">{c.input_tokens + (c.cache_read_input_tokens || 0)} in · {c.output_tokens} out{c.tool_calls?.length ? ` · asked for ${c.tool_calls.join(', ')}` : ''}</span>
          <span className="ms-auto hub-menu-item-id">{c.first_token_ms != null ? `first words ${ms(c.first_token_ms)} · ` : ''}{ms(c.ms)}</span>
        </div>
      ))}
      {docs.length > 0 && <h4 className="hub-block-title mt-4">Document passages read</h4>}
      {docs.map((d, i) => (
        <details key={i} className="hub-trace">
          <summary><Icon name="doc" size={14} style={{ color: 'var(--brand-hi)' }} /><span>{d.title}</span><span className="ms-auto hub-menu-item-id">p. {d.page} · {d.section}</span></summary>
          <div className="hub-trace-body"><p>{d.text}</p></div>
        </details>
      ))}
    </Sheet>
  );
}

export function SourceSheet({ source, onClose }) {
  return (
    <Sheet title={source.title} icon="doc" onClose={onClose} width={520}>
      <div className="hub-kv mb-3">
        {source.collection && <div className="hub-kv-row"><span className="hub-kv-label">Collection</span><span className="hub-kv-value">{source.collection}</span></div>}
        {source.page != null && <div className="hub-kv-row"><span className="hub-kv-label">Page</span><span className="hub-kv-value">{source.page}</span></div>}
        {source.section && <div className="hub-kv-row"><span className="hub-kv-label">Section</span><span className="hub-kv-value">{source.section}</span></div>}
      </div>
      <p className="hub-passage">{source.text}</p>
    </Sheet>
  );
}

export function AccessGate({ onUnlocked }) {
  const [code, setCode] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    if (!code.trim() || busy) return;
    setBusy(true);
    setError(null);
    try { await unlock(code.trim()); onUnlocked(); } catch (err) { setError(err.message); }
    setBusy(false);
  };
  return (
    <div className="h-full flex items-center justify-center p-6">
      <form onSubmit={submit} className="glass-card p-7 w-full max-w-[380px] animate-slide-up">
        <h2 className="text-[17px] font-extrabold mb-1" style={{ color: 'var(--text)' }}>Enter the access code</h2>
        <p className="text-[12.5px] mb-4" style={{ color: 'var(--text-dim)' }}>This assistant is shared by invitation. Enter the code you were given.</p>
        <input autoFocus type="password" value={code} onChange={(e) => setCode(e.target.value)} placeholder="Access code" className="hub-field" />
        {error && <p className="text-[12px] mt-2" style={{ color: 'var(--red)' }}>{error}</p>}
        <button type="submit" disabled={busy || !code.trim()} className="hub-btn is-primary w-full mt-4 justify-center">{busy ? 'Checking…' : 'Continue'}</button>
      </form>
    </div>
  );
}
