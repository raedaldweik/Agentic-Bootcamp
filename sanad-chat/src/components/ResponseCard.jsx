import { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ToolCallTrace from './ToolCallTrace';
import ChartCard from './ChartCard';
import ReportCard from './ReportCard';
import { useStrings } from '../lib/strings';
import { extractChartSpecs } from '../lib/chartSpec';
import { extractReportImages } from '../lib/reportSpec';

const sourceLabel = (doc, i) => {
  const meta = doc?.metadata || {};
  const name = meta.filename || meta.source || meta.file_name || meta.title || `Source ${i + 1}`;
  return meta.page != null ? `${name} · p.${meta.page}` : name;
};

const auto = (Tag) => ({ node, ...props }) => <Tag dir="auto" {...props} />;
const md = {
  a: ({ node, ...props }) => <a target="_blank" rel="noreferrer" {...props} />,
  table: ({ node, ...props }) => <div className="overflow-x-auto"><table dir="auto" {...props} /></div>,
  p: auto('p'), li: auto('li'), h1: auto('h1'), h2: auto('h2'), h3: auto('h3'), blockquote: auto('blockquote'),
};

/** Renders one normalized agent response: answer, charts, sources, tool calls, usage. */
export default function ResponseCard({ data, onOpenSource, onOpenDetails }) {
  const { t } = useStrings();
  const [copied, setCopied] = useState(false);
  const chartSpecs = useMemo(() => extractChartSpecs(data), [data]);
  const reportSpecs = useMemo(() => extractReportImages(data), [data]);
  if (!data) return null;
  const usage = data.usage || {};
  const hasUsage = usage.llmTotalTokens != null || usage.llmTotalCost != null;

  const copy = async () => {
    try { await navigator.clipboard.writeText(data.answer || ''); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ }
  };

  return (
    <div className="sn-answer a-reveal">
      <div className="sn-bot">
        <div className="sn-md">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={md}>{data.answer || '_(empty answer)_'}</ReactMarkdown>
        </div>
      </div>

      {chartSpecs.map((spec, i) => <ChartCard key={i} spec={spec} />)}
      {reportSpecs.map((spec, i) => <ReportCard key={i} spec={spec} />)}

      {data.context && data.context.length > 0 && (
        <div className="sn-sources">
          <span className="sn-sources-label">{t('sources')}</span>
          {data.context.map((doc, i) => (
            <button key={i} className="sn-source-chip" onClick={() => onOpenSource?.(doc)} title={t('viewPassage')}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="shrink-0"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></svg>
              <span>{sourceLabel(doc, i)}</span>
            </button>
          ))}
        </div>
      )}

      <ToolCallTrace toolCalls={data.toolCalls} />

      <div className="sn-footer">
        {onOpenDetails && (
          <button className="sn-mini-btn accent" onClick={() => onOpenDetails(data)} title={t('flightRecorderHint')}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 3" /></svg>
            {t('flightRecorder')}
          </button>
        )}
        <button className="sn-mini-btn" onClick={copy}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></svg>
          {copied ? t('copied') : t('copy')}
        </button>
        {hasUsage && (
          <>
            <span className="sep">·</span>
            {usage.llmTotalTokens != null && <span>{usage.llmTotalTokens.toLocaleString()} {t('tokens')}</span>}
            {usage.llmPromptTokens != null && <span>{t('promptCompletion', { p: usage.llmPromptTokens.toLocaleString(), c: usage.llmCompletionTokens?.toLocaleString() ?? 0 })}</span>}
            {usage.llmTotalCost != null && <span>${Number(usage.llmTotalCost).toFixed(4)}</span>}
          </>
        )}
      </div>
    </div>
  );
}
