import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { streamCrcChat } from '../services/api';

/* The screening assistant: a small chat that knows the person's form and result, answers
   questions about the tests, the programme and where to go. Model-backed when the app has a
   model key; a built-in set of answers otherwise, so it always says something sensible. */
const SUGGESTED = [
  'What does my tier mean?',
  'What is a FIT test?',
  'How do I prepare for a colonoscopy?',
  'Why does screening start at 40 here?',
  'Where do I book?',
];
const HELLO = { role: 'assistant', content: 'Ask me anything about your result: the tests, what the numbers mean, the UAE programme, or where to go. I know what you entered on the left.' };

export default function ScreeningChat({ person }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([HELLO]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState(null);
  const endRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, open]);

  const send = async (text) => {
    const q = (text ?? input).trim();
    if (!q || busy) return;
    setInput('');
    const history = [...messages.filter((m) => m !== HELLO), { role: 'user', content: q }];
    setMessages([...messages, { role: 'user', content: q }, { role: 'assistant', content: '', streaming: true }]);
    setBusy(true);
    abortRef.current?.abort();
    const ctl = new AbortController(); abortRef.current = ctl;
    let acc = '';
    try {
      await streamCrcChat({ person, messages: history }, (ev) => {
        if (ev.type === 'meta') setMode(ev.mode);
        if (ev.type === 'token') { acc += ev.text; setMessages((m) => m.map((x, i) => i === m.length - 1 ? { ...x, content: acc } : x)); }
        if (ev.type === 'final') setMessages((m) => m.map((x, i) => i === m.length - 1 ? { role: 'assistant', content: ev.text || acc } : x));
      }, ctl.signal);
    } catch (e) {
      if (e.name !== 'AbortError') setMessages((m) => m.map((x, i) => i === m.length - 1 ? { role: 'assistant', content: 'I could not answer just now. Try again in a moment.', error: true } : x));
    }
    setBusy(false);
  };

  return (
    <>
      {!open && (
        <button className="scr-chat-fab" onClick={() => setOpen(true)} title="Ask about your result">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
          Ask about my result
        </button>
      )}
      {open && (
        <div className="scr-chat" role="dialog" aria-label="Screening assistant">
          <div className="scr-chat-head">
            <div>
              <div className="scr-chat-title">Screening assistant</div>
              <div className="scr-chat-sub">{mode === 'live' ? 'Answers from the model, grounded in your result' : mode === 'deterministic' ? 'Built-in answers · no model connected' : 'Knows what you entered on the left'}</div>
            </div>
            <button className="team-gate-close" style={{ position: 'static' }} onClick={() => setOpen(false)} aria-label="Close">×</button>
          </div>
          <div className="scr-chat-body">
            {messages.map((m, i) => (
              <div key={i} className={`scr-msg ${m.role} ${m.error ? 'err' : ''}`}>
                {m.role === 'assistant'
                  ? (m.content ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown> : <span className="scr-typing"><i /><i /><i /></span>)
                  : m.content}
              </div>
            ))}
            <div ref={endRef} />
          </div>
          {messages.length <= 2 && (
            <div className="scr-chat-sugg">
              {SUGGESTED.map((q) => <button key={q} className="sim-chip" onClick={() => send(q)} disabled={busy}>{q}</button>)}
            </div>
          )}
          <form className="scr-chat-input" onSubmit={(e) => { e.preventDefault(); send(); }}>
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Type a question…" disabled={busy} />
            <button type="submit" disabled={busy || !input.trim()} aria-label="Send">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
            </button>
          </form>
          <div className="scr-chat-foot">Educational prototype. Not a diagnosis. Symptoms need a doctor, not a chat.</div>
        </div>
      )}
    </>
  );
}
