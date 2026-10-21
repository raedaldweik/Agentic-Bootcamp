import { useState } from 'react';
import { useStrings } from '../lib/strings';

const fmt = (v) => {
  if (v == null) return '';
  if (typeof v === 'string') return v;
  try { return JSON.stringify(v); } catch { return String(v); }
};

/** Collapsible trace of the tool calls the agent made while answering. */
export default function ToolCallTrace({ toolCalls }) {
  const { t } = useStrings();
  const [open, setOpen] = useState(false);
  if (!toolCalls || toolCalls.length === 0) return null;

  return (
    <div className="sn-trace">
      <button className="sn-trace-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 3" /></svg>
        <span>{t('toolCallsHeader', { n: toolCalls.length, s: toolCalls.length !== 1 ? 's' : '' })}</span>
        <span className="flex-1" />
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }}><polyline points="6 9 12 15 18 9" /></svg>
      </button>
      {open && (
        <div className="a-fade-up">
          {toolCalls.map((call, i) => (
            <div key={i} className="sn-trace-step">
              <div className="sn-trace-num">{i + 1}</div>
              <div className="flex-1 min-w-0">
                <span className="sn-trace-tool">{call.toolName || call.name || 'tool'}</span>
                {call.input && <div className="sn-trace-io">in: {fmt(call.input).slice(0, 400)}</div>}
                {call.output && <div className="sn-trace-io">out: {fmt(call.output).slice(0, 400)}</div>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
