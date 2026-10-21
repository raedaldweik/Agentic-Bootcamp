import { useRef } from 'react';
import { useStrings } from '../lib/strings';
import VoiceInput from './VoiceInput';

const AttachIcon = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
  </svg>
);
const SendIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
  </svg>
);

/** The floating input bar: attach · text · voice · send, with a scan line while the agent works. */
export default function Composer({
  input, setInput, onSend, loading, target, inputRef,
  attachment, attaching, attachError, onPickFile, onClearAttachment, onClearError,
}) {
  const { t } = useStrings();
  const fileRef = useRef(null);

  const grow = (el) => { if (!el) return; el.style.height = 'auto'; el.style.height = `${Math.min(el.scrollHeight, 180)}px`; };
  const canSend = !!input.trim() && !loading && !!target;

  return (
    <div className="sn-composer-wrap">
      {(attachment || attaching || attachError) && (
        <div className="sn-attach-bar a-fade-up">
          {attachError ? (
            <div className="sn-chip err">{attachError}<button onClick={onClearError}>✕</button></div>
          ) : attaching ? (
            <div className="sn-chip"><span className="sn-dot ok pulse" />{t('readingDocument')}</div>
          ) : (
            <div className="sn-chip">
              <AttachIcon size={12} />
              <span className="font-semibold truncate">{attachment.name}</span>
              <span className="muted">
                {attachment.truncated ? t('firstKChars', { n: Math.round(attachment.text.length / 1000) }) : t('kChars', { n: (attachment.chars / 1000).toFixed(1) })}
                {' '}{t('sentWithNext')}
              </span>
              <button onClick={onClearAttachment}>✕</button>
            </div>
          )}
        </div>
      )}

      <div className={`sn-composer ${loading ? 'loading' : ''}`}>
        {loading && <div className="sn-scan" />}
        <input ref={fileRef} type="file" accept=".pdf,.docx,.doc,.txt,.md,.csv,.json,.xlsx,.pptx" className="hidden" onChange={onPickFile} />
        <button className="sn-icon-btn" onClick={() => fileRef.current?.click()} disabled={attaching || loading} title={t('attachTooltip')} aria-label={t('attachTooltip')}>
          <AttachIcon />
        </button>
        <textarea ref={inputRef} rows="1" value={input}
          onChange={e => { setInput(e.target.value); grow(e.target); }}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend(); } }}
          placeholder={target ? t('askAnything', { name: target.name }) : t('selectThenAsk')}
          aria-label={t('send')} />
        <VoiceInput disabled={loading} title={t('speakTooltip')}
          onTranscript={(text) => { setInput(prev => (prev ? `${prev} ${text}` : text)); inputRef.current?.focus(); }} />
        <button className="sn-send" onClick={() => onSend()} disabled={!canSend} title={t('send')} aria-label={t('send')}>
          {SendIcon}
        </button>
      </div>

      <div className="sn-hint">
        <span>{t('composerHint')}</span>
        {target && (
          <span className="target">
            <span className="sn-dot ok" style={{ width: 6, height: 6 }} />
            <span className="truncate" style={{ maxWidth: 260 }}>{target.name}</span>
          </span>
        )}
      </div>
    </div>
  );
}
