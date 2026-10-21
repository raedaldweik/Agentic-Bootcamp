import { useEffect } from 'react';
import { useStrings } from '../lib/strings';

/** Modal that shows the retrieved passage that grounded an answer. */
export default function SourceViewer({ source, onClose }) {
  const { t } = useStrings();
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  if (!source) return null;
  const meta = source.metadata || {};
  const title = meta.filename || meta.source || meta.file_name || meta.title || t('retrievedPassage');

  return (
    <div className="sn-backdrop" onClick={onClose}>
      <div className="sn-modal" style={{ maxWidth: 680 }} onClick={e => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="sn-modal-head">
          <div className="sn-modal-title">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--cyan)" strokeWidth="2" className="shrink-0"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></svg>
            <span className="truncate">{title}</span>
            {meta.page != null && <span className="sn-pill">p. {meta.page}</span>}
          </div>
          <button className="sn-icon-btn" onClick={onClose} aria-label={t('close')}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
          </button>
        </div>
        <div className="sn-modal-body">
          <p className="sn-passage">{source.pageContent || source.page_content || source.content || '(no text content)'}</p>
        </div>
      </div>
    </div>
  );
}
