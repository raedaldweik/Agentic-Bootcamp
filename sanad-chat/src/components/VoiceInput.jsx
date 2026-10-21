import { useState, useRef, useCallback } from 'react';

const MicIcon = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" /><path d="M19 10v2a7 7 0 0 1-14 0v-2" /><line x1="12" y1="19" x2="12" y2="23" /><line x1="8" y1="23" x2="16" y2="23" />
  </svg>
);

/** Browser speech recognition, where the browser supports it. */
export default function VoiceInput({ onTranscript, disabled, title }) {
  const [listening, setListening] = useState(false);
  const ref = useRef(null);

  const toggle = useCallback(() => {
    if (listening) { ref.current?.stop(); setListening(false); return; }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { alert('Speech recognition is not supported in this browser'); return; }
    const rec = new SR();
    rec.lang = 'en-US';
    rec.continuous = false;
    rec.interimResults = false;
    rec.onresult = (e) => { onTranscript?.(e.results[0][0].transcript); setListening(false); };
    rec.onerror = () => setListening(false);
    rec.onend = () => setListening(false);
    ref.current = rec;
    rec.start();
    setListening(true);
  }, [listening, onTranscript]);

  return (
    <button onClick={toggle} disabled={disabled} title={title} className={`sn-icon-btn ${listening ? 'listening' : ''}`} aria-pressed={listening}>
      {listening && <span className="sn-ping" />}
      {MicIcon}
    </button>
  );
}
