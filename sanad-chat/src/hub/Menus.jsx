// The two controls that set the context of a question: who is asking, and the shop time.
import { useEffect, useRef, useState } from 'react';
import Icon from './Icon';

function useDismiss(open, close) {
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) close(); };
    const onKey = (e) => { if (e.key === 'Escape') close(); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey); };
  }, [open, close]);
  return ref;
}

export function PersonaMenu({ personas, value, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  const current = personas.find((p) => p.key === value) || personas[0];
  if (!current) return null;
  return (
    <div className="relative" ref={ref}>
      <button className="hub-control" onClick={() => setOpen((o) => !o)} aria-haspopup="listbox" aria-expanded={open} title="Choose who is asking">
        <span className="hub-avatar">{current.initials}</span>
        <span className="hub-control-text">
          <span className="hub-control-label">Asking as</span>
          <span className="hub-control-value">{current.title}</span>
        </span>
        <Icon name="chevron" size={14} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="hub-menu animate-fade-up" role="listbox" style={{ width: 340 }}>
          <div className="hub-menu-title">Who is asking?</div>
          {personas.map((p) => (
            <button key={p.key} role="option" aria-selected={p.key === value}
              className={`hub-menu-item ${p.key === value ? 'is-active' : ''}`}
              onClick={() => { onChange(p.key); setOpen(false); }}>
              <span className="hub-avatar">{p.initials}</span>
              <span className="min-w-0 flex-1 text-start">
                <span className="hub-menu-item-title">{p.title} <span className="hub-menu-item-id">{p.id}</span></span>
                <span className="hub-menu-item-sub">{p.blurb}</span>
              </span>
              {p.key === value && <Icon name="check" size={15} style={{ color: 'var(--brand-hi)' }} />}
            </button>
          ))}
          <div className="hub-menu-foot">The role sets what the assistant may do for you. Anyone may see any status.</div>
        </div>
      )}
    </div>
  );
}

const pad = (n) => String(n).padStart(2, '0');
const toInput = (ts) => (ts || '').replace(' ', 'T');
const fromInput = (v) => (v || '').replace('T', ' ').slice(0, 16);
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export function niceTime(ts) {
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(ts || '');
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${pad(m[4])}:${m[5]}` : ts;
}

export function ClockMenu({ moments, value, onChange }) {
  const [open, setOpen] = useState(false);
  const [custom, setCustom] = useState(toInput(value));
  const ref = useDismiss(open, () => setOpen(false));
  useEffect(() => { setCustom(toInput(value)); }, [value]);
  const moment = moments.find((m) => m.ts === value);
  return (
    <div className="relative" ref={ref}>
      <button className="hub-control" onClick={() => setOpen((o) => !o)} aria-haspopup="listbox" aria-expanded={open} title="Set the shop time">
        <span className="hub-control-icon"><Icon name="clock" size={15} /></span>
        <span className="hub-control-text">
          <span className="hub-control-label">Shop time</span>
          <span className="hub-control-value">{niceTime(value)}</span>
        </span>
        <Icon name="chevron" size={14} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="hub-menu animate-fade-up" role="listbox" style={{ width: 330 }}>
          <div className="hub-menu-title">Shop time</div>
          {moments.map((m, i) => (
            <button key={m.id} role="option" aria-selected={m.ts === value}
              className={`hub-menu-item ${m.ts === value ? 'is-active' : ''}`}
              onClick={() => { onChange(m.ts); setOpen(false); }}>
              <span className="hub-step-n" style={{ width: 22, height: 22, fontSize: 11 }}>{i + 1}</span>
              <span className="min-w-0 flex-1 text-start">
                <span className="hub-menu-item-title">{m.label} <span className="hub-menu-item-id">{niceTime(m.ts)}</span></span>
                <span className="hub-menu-item-sub">{m.detail}</span>
              </span>
              {m.ts === value && <Icon name="check" size={15} style={{ color: 'var(--brand-hi)' }} />}
            </button>
          ))}
          <div className="hub-menu-custom">
            <label htmlFor="hub-clock">Any other time</label>
            <div className="flex gap-2">
              <input id="hub-clock" type="datetime-local" value={custom} min="2026-10-20T00:00" max="2026-11-20T00:00"
                onChange={(e) => setCustom(e.target.value)} />
              <button disabled={!custom || fromInput(custom) === value} onClick={() => { onChange(fromInput(custom)); setOpen(false); }}>Set</button>
            </div>
          </div>
          <div className="hub-menu-foot">
            A demonstration clock. The shop data is shown as it stood at this time{moment ? '' : ' (custom)'}, so the same question can have a different answer later in the day.
          </div>
        </div>
      )}
    </div>
  );
}
