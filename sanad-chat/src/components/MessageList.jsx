import { useStrings } from '../lib/strings';
import { SUGGESTIONS } from '../lib/strings';
import ResponseCard from './ResponseCard';
import { SanadMark, Turbine } from './Logo';

const SuggestIcon = {
  trend: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 17 9 11 13 15 21 7" /><polyline points="14 7 21 7 21 14" /></svg>,
  bars: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="5" y1="20" x2="5" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="19" y1="20" x2="19" y2="14" /></svg>,
  pie: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21.21 15.89A10 10 0 1 1 8 2.83" /><path d="M22 12A10 10 0 0 0 12 2v10z" /></svg>,
  doc: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="8" y1="13" x2="16" y2="13" /><line x1="8" y1="17" x2="14" y2="17" /></svg>,
};

const AttachIcon = (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
  </svg>
);

const BotAvatar = () => <div className="sn-avatar"><SanadMark size={18} /></div>;

// Flatten a trace into display steps for the live activity timeline
function traceSteps(trace, t) {
  if (!trace) return [];
  return [
    ...(trace.retrievalCalls || []).map(c => ({ key: `r-${c.id}`, kind: 'rag', label: t('stepRetrieval') })),
    ...(trace.toolCalls || []).map(c => ({ key: `t-${c.id}`, kind: 'tool', label: c.toolName || t('stepTool') })),
    ...(trace.llmCalls || []).map(c => ({ key: `l-${c.id}`, kind: 'llm', label: c.input?.modelName || t('stepLlm') })),
  ];
}

function Hero({ onSuggest, target }) {
  const { t } = useStrings();
  return (
    <div className="sn-hero">
      <div className="sn-turbine"><Turbine /></div>
      <div className="sn-hero-mark"><SanadMark size={64} /></div>
      <div className="sn-hero-eyebrow">{t('heroEyebrow')}</div>
      <h1 className="sn-hero-title">{t('heroTitle')}</h1>
      <p className="sn-hero-sub">{t('heroSub')}</p>
      <div className="sn-suggest-grid">
        {SUGGESTIONS.map((s, i) => (
          <button key={i} className="sn-suggest a-fade-up" style={{ animationDelay: `${0.08 * i + 0.1}s` }}
            onClick={() => onSuggest(s.prompt)} disabled={!target} title={s.prompt}>
            <span className="sn-suggest-ico">{SuggestIcon[s.icon]}</span>
            <span className="min-w-0">
              <span className="sn-suggest-title block">{s.title}</span>
              <span className="sn-suggest-text block">{s.prompt}</span>
            </span>
          </button>
        ))}
      </div>
      <div className="sn-hero-hint">
        <span className="sn-kbd">/</span><span>{t('heroHint')}</span>
      </div>
    </div>
  );
}

function LiveActivity({ liveTrace }) {
  const { t } = useStrings();
  const steps = traceSteps(liveTrace, t);
  return (
    <div className="sn-row a-fade-up">
      <BotAvatar />
      <div className="sn-bubble-col">
        <div className="sn-bot sn-live">
          {steps.length > 0 && (
            <div className="sn-live-steps">
              {steps.slice(-6).map((s, i, arr) => (
                <div key={s.key} className={`sn-live-step a-fade-up ${i === arr.length - 1 ? 'current' : ''}`}>
                  <span className="node" />
                  <span className="kind">{s.kind}</span>
                  <span className="label">{s.label}</span>
                </div>
              ))}
            </div>
          )}
          <div className="flex items-center gap-3">
            <span className="sn-dots"><span /><span /><span /></span>
            <span className="text-[11px]" style={{ color: 'var(--text-faint)' }}>
              {steps.length > 0 ? t('stepsSoFar', { n: steps.length, s: steps.length !== 1 ? 's' : '' }) : t('thinking')}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

/** The conversation: welcome hero when empty, otherwise the message stream + live activity. */
export default function MessageList({ messages, loading, liveTrace, target, onSuggest, onOpenSource, onOpenDetails, endRef }) {
  const { t } = useStrings();
  const visible = messages.filter(m => m.type !== 'welcome');
  const heroMode = visible.length === 0 && !loading;

  return (
    <div className={`sn-stream ${heroMode ? 'hero-mode' : ''}`}>
      {heroMode ? <Hero onSuggest={onSuggest} target={target} /> : visible.map((msg, i) => (
        <div key={i} className={`sn-row a-fade-up ${msg.role === 'user' ? 'user' : ''}`}>
          {msg.role === 'user' ? <div className="sn-avatar user">{t('you')}</div> : <BotAvatar />}
          <div className="sn-bubble-col">
            {msg.type === 'structured' ? (
              <ResponseCard data={msg.data} onOpenSource={onOpenSource}
                onOpenDetails={(d) => onOpenDetails({ data: d, query: msg.query })} />
            ) : msg.role === 'user' ? (
              <div className="sn-user" dir="auto">
                {msg.attachmentName && <div className="sn-attach-chip">{AttachIcon}{msg.attachmentName}</div>}
                {msg.content}
              </div>
            ) : (
              <div className={`sn-bot ${msg.isError ? 'error' : ''}`}>{msg.content}</div>
            )}
          </div>
        </div>
      ))}
      {loading && <LiveActivity liveTrace={liveTrace} />}
      <div ref={endRef} />
    </div>
  );
}
