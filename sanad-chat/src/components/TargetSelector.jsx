import { useEffect, useState } from 'react';
import { useLanguage } from '../lib/LanguageContext';

const AgentIcon = (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 2l1.8 4.6L18 8l-4.2 1.4L12 14l-1.8-4.6L6 8l4.2-1.4z" /><path d="M5 16l.9 2.1L8 19l-2.1.9L5 22l-.9-2.1L2 19l2.1-.9z" /><path d="M19 15l.7 1.6 1.6.7-1.6.7L19 19.6l-.7-1.6-1.6-.7 1.6-.7z" />
  </svg>
);
const CollectionIcon = (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
  </svg>
);

/** Dropdown to pick which RAM agent (or collection) the chat talks to. */
export default function TargetSelector({ agents, collections, target, onChange, loading, error }) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const all = [
    ...agents.map(a => ({ ...a, type: 'agent' })),
    ...collections.map(c => ({ ...c, type: 'collection' })),
  ];
  const selected = target ? all.find(x => x.type === target.type && x.id === target.id) : null;
  const pick = (item) => { onChange({ type: item.type, id: item.id, name: item.name }); setOpen(false); };

  const Group = ({ label, items, type }) => items.length > 0 && (
    <div>
      <p className="sn-group-label">{label}</p>
      {items.map(item => {
        const active = target && target.type === type && target.id === item.id;
        return (
          <button key={item.id} className={`sn-target-item ${active ? 'active' : ''}`} onClick={() => pick({ ...item, type })}>
            <span className="ico">{type === 'agent' ? AgentIcon : CollectionIcon}</span>
            <span className="body">
              <span className="name block truncate">{item.name}</span>
              {item.description && <span className="desc block">{item.description}</span>}
            </span>
          </button>
        );
      })}
    </div>
  );

  const dot = error ? 'err' : selected ? 'ok' : 'warn';
  return (
    <div className="sn-target">
      <button className="sn-target-btn" onClick={() => setOpen(!open)} aria-haspopup="listbox" aria-expanded={open}>
        <span className={`sn-dot ${dot} ${loading ? 'pulse' : ''}`} />
        <span className="name">
          {loading ? t('connecting') : error ? t('serviceUnreachable') : selected ? selected.name : t('selectAgent')}
        </span>
        {selected && <span className="sn-pill cyan">{t(selected.type)}</span>}
        <svg className={`chev ${open ? 'open' : ''}`} width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="6 9 12 15 18 9" /></svg>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-50" onClick={() => setOpen(false)} />
          <div className="sn-target-menu" role="listbox">
            {error ? (
              <p className="px-3 py-3 text-[11.5px]" style={{ color: 'var(--red)' }}>{error}</p>
            ) : all.length === 0 ? (
              <p className="px-3 py-3 text-[11.5px]" style={{ color: 'var(--text-dim)' }}>{t('noAgents')}</p>
            ) : (
              <div className="pb-1">
                <Group label={t('agents')} items={agents} type="agent" />
                <Group label={t('collections')} items={collections} type="collection" />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
