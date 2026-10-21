import { useState, useEffect } from 'react';
import { getQueryTrace } from '../lib/api';
import { useLanguage } from '../lib/LanguageContext';

const fmt = (v) => {
  if (v == null) return '';
  if (typeof v === 'string') return v;
  try { return JSON.stringify(v, null, 2); } catch { return String(v); }
};

function Section({ title, count, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="sn-section">
      <button className="sn-section-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <svg className={`chev ${open ? 'open' : ''}`} width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="9 18 15 12 9 6" /></svg>
        <span>{title}</span>
        {count != null && <span className="sn-pill">{count}</span>}
      </button>
      {open && <div className="sn-section-body">{children}</div>}
    </div>
  );
}

function Mono({ label, value, max = 4000 }) {
  if (value == null || value === '') return null;
  const text = fmt(value);
  return (
    <div>
      {label && <p className="sn-label">{label}</p>}
      <pre className="sn-mono">{text.slice(0, max)}{text.length > max ? '\n… (truncated)' : ''}</pre>
    </div>
  );
}

/**
 * Flight recorder — full traceability for one answer: the question, tool
 * calls with inputs/outputs, LLM calls, retrieval (RAG) calls, retrieved
 * passages and token usage, pulled from RAM's trace for this query.
 */
export default function QueryDetails({ data, query, onClose, onOpenSource }) {
  const { t } = useLanguage();
  const [trace, setTrace] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    if (!data?.queryId) { setLoading(false); return; }
    getQueryTrace(data.queryId).then(setTrace).catch(() => setTrace(null)).finally(() => setLoading(false));
  }, [data?.queryId]);

  if (!data) return null;
  const usage = data.usage || {};
  const toolCalls = trace?.toolCalls?.length ? trace.toolCalls : (data.toolCalls || []);
  const llmCalls = trace?.llmCalls || [];
  const retrievalCalls = trace?.retrievalCalls || [];
  const context = data.context || [];

  return (
    <div className="sn-backdrop" onClick={onClose}>
      <div className="sn-modal" style={{ maxWidth: 800 }} onClick={e => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="sn-modal-head">
          <div className="sn-modal-title">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--cyan)" strokeWidth="2" className="shrink-0"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 3" /></svg>
            <span>
              {t('flightRecorder')}
              <span className="sub">{loading ? t('loadingTrace') : t('flightRecorderHint')}</span>
            </span>
          </div>
          <button className="sn-icon-btn" onClick={onClose} aria-label={t('close')}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
          </button>
        </div>

        <div className="sn-modal-body">
          <div className="sn-question">
            <p className="sn-label">{t('inputPrompt')}</p>
            {query || data.content || '(unknown)'}
          </div>

          <div className="flex flex-wrap gap-2">
            {data.target && <span className="sn-pill">target: {data.target}</span>}
            {usage.llmTotalTokens != null && <span className="sn-pill">{usage.llmTotalTokens.toLocaleString()} {t('tokens')}</span>}
            {usage.llmPromptTokens != null && <span className="sn-pill">{usage.llmPromptTokens.toLocaleString()} prompt / {usage.llmCompletionTokens?.toLocaleString() ?? 0} completion</span>}
            {usage.llmTotalCost != null && <span className="sn-pill sand">${Number(usage.llmTotalCost).toFixed(4)}</span>}
            {data.queryId && <span className="sn-pill">query {String(data.queryId).slice(0, 8)}…</span>}
          </div>

          <Section title={t('toolCallsSection')} count={toolCalls.length} defaultOpen={toolCalls.length > 0}>
            {toolCalls.length === 0 && <p className="text-[11.5px]" style={{ color: 'var(--text-dim)' }}>{t('noToolCalls')}</p>}
            {toolCalls.map((c, i) => (
              <div key={c.id || i} className="sn-card">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="sn-trace-num">{i + 1}</span>
                  <span className="sn-trace-tool">{c.toolName || 'tool'}</span>
                  {c.output?.isError && <span className="sn-pill err">error</span>}
                  {c.cost != null && c.cost > 0 && <span className="sn-pill sand">${Number(c.cost).toFixed(4)}</span>}
                </div>
                <Mono label={t('inputLabel')} value={c.input} />
                <Mono label={t('outputLabel')} value={c.output?.structuredContent ?? c.output?.content ?? c.output} />
              </div>
            ))}
          </Section>

          <Section title={t('retrievalSection')} count={retrievalCalls.length}>
            {retrievalCalls.length === 0 && <p className="text-[11.5px]" style={{ color: 'var(--text-dim)' }}>{t('noRetrieval')}</p>}
            {retrievalCalls.map((c, i) => (
              <div key={c.id || i} className="sn-card">
                <Mono label={t('inputLabel')} value={c.input} />
                <Mono label={t('outputLabel')} value={c.output} />
              </div>
            ))}
          </Section>

          <Section title={t('llmSection')} count={llmCalls.length}>
            {llmCalls.length === 0 && <p className="text-[11.5px]" style={{ color: 'var(--text-dim)' }}>{t('noLlm')}</p>}
            {llmCalls.map((c, i) => (
              <div key={c.id || i} className="sn-card">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="sn-trace-tool">{c.input?.modelName || c.llmId || 'LLM'}</span>
                  {c.input?.modelProvider && <span className="sn-pill">{c.input.modelProvider}</span>}
                  {c.input?.temperature != null && <span className="sn-pill">temp {c.input.temperature}</span>}
                  {(c.promptTokens != null || c.completionTokens != null) && <span className="sn-pill">{c.promptTokens ?? 0} prompt / {c.completionTokens ?? 0} completion tok</span>}
                  {(c.promptCost != null || c.completionCost != null) && <span className="sn-pill sand">${(Number(c.promptCost || 0) + Number(c.completionCost || 0)).toFixed(4)}</span>}
                </div>
                <Mono label={t('promptLabel')} value={c.input?.content} />
                <Mono label={t('responseLabel')} value={c.output?.response} />
              </div>
            ))}
          </Section>

          <Section title={t('contextSection')} count={context.length}>
            {context.length === 0 && <p className="text-[11.5px]" style={{ color: 'var(--text-dim)' }}>{t('noContext')}</p>}
            {context.map((doc, i) => {
              const meta = doc?.metadata || {};
              const label = meta.filename || meta.source || meta.file_name || meta.title || `Source ${i + 1}`;
              return (
                <div key={i} className="sn-card">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] font-semibold truncate" style={{ color: 'var(--sky)' }}>{label}</span>
                    {meta.page != null && <span className="sn-pill">p. {meta.page}</span>}
                    {onOpenSource && <button onClick={() => onOpenSource(doc)} className="sn-mini-btn accent ms-auto shrink-0">{t('open')}</button>}
                  </div>
                  <p className="sn-passage max-h-[140px] overflow-y-auto" style={{ fontSize: 11.5 }}>
                    {doc.pageContent || doc.page_content || doc.content || '(no text)'}
                  </p>
                </div>
              );
            })}
          </Section>
        </div>
      </div>
    </div>
  );
}
