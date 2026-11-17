// Speaking to the assistant, and having it read answers back.
//
// Listening uses the browser's speech recognition (Chrome, Edge, Safari). Words appear as
// they are heard; when the person stops, the final text is tidied (shop ids such as
// "t one one seven" or "engine 204" come back as T-117 and ENG-204) and handed over.
import { useCallback, useEffect, useRef, useState } from 'react';

const SR = typeof window !== 'undefined' ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;
export const voiceSupported = !!SR;
export const speechSupported = typeof window !== 'undefined' && 'speechSynthesis' in window;

const ERRORS = {
  'not-allowed': 'Microphone access is blocked. Allow the microphone for this site in the browser, then try again.',
  'service-not-allowed': 'Speech recognition is switched off in this browser. Allow it in the browser settings.',
  'audio-capture': 'No microphone was found. Check that one is connected.',
  'no-speech': "I didn't hear anything. Tap the microphone and speak.",
  network: 'Speech recognition could not reach its service. Check the connection and try again.',
  'language-not-supported': 'This browser cannot recognise English speech.',
};

const DIGIT = { zero: '0', oh: '0', o: '0', one: '1', two: '2', to: '2', too: '2', three: '3', four: '4', for: '4', five: '5', six: '6', seven: '7', eight: '8', ate: '8', nine: '9' };
const NUM = '(?:zero|oh|one|two|three|four|five|six|seven|eight|nine)';

/** Tidy a transcript: shop ids are spoken in many ways and written in one. */
export function tidyTranscript(text) {
  let s = ` ${text.trim()} `;
  // "one one seven" after an id letter becomes digits: "t one one seven" -> "t 117"
  s = s.replace(new RegExp(`\\b(t|tee|tea|p|pee|k|kay|eng|engine|e n g|fan)((?:[\\s-]+${NUM}){3,4})\\b`, 'gi'),
    (_, head, nums) => `${head} ${nums.trim().split(/[\s-]+/).map((w) => DIGIT[w.toLowerCase()] ?? w).join('')}`);
  s = s.replace(/\b(\d)\s(\d)\s(\d)(?:\s(\d))?\b/g, (_, a, b, c, d) => `${a}${b}${c}${d || ''}`);
  s = s.replace(/\b(?:e\.?\s?n\.?\s?g\.?|eng|engine)[\s-]*(?:number\s*)?(\d{3})\b/gi, 'ENG-$1');
  s = s.replace(/\b(?:j\.?\s?c\.?|jay\s?see|job card)[\s-]*fan[\s-]*(\d{3})\b/gi, 'JC-FAN-$1');
  s = s.replace(/\b(?:tool\s+)?(?:t|tee|tea)[\s-]*(\d{3})\b/gi, (m, n) => (/^tool/i.test(m) ? `tool T-${n}` : `T-${n}`));
  s = s.replace(/\b(?:p|pee|pea)[\s-]*(\d{4})\b/gi, 'P-$1');
  s = s.replace(/\b(?:k|kay)[\s-]*(\d{3})\b/gi, 'K-$1');
  s = s.replace(/\bgate\s+(one|two|three)\b/gi, (_, w) => `Gate ${DIGIT[w.toLowerCase()]}`);
  s = s.trim().replace(/\s{2,}/g, ' ').replace(/\bi\b/g, 'I');
  if (!s) return s;
  s = s[0].toUpperCase() + s.slice(1);
  if (!/[.?!]$/.test(s)) s += /^(who|what|when|where|why|which|how|is|are|can|could|do|does|did|has|have|will|would|should|may)\b/i.test(s) ? '?' : '.';
  return s;
}

/**
 * useVoice({ onFinal }): { supported, listening, interim, error, start, stop, clearError }
 * `interim` is what has been heard so far; `onFinal(text)` fires once with the tidied text.
 */
export function useVoice({ onFinal, lang = 'en-US' } = {}) {
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState('');
  const [error, setError] = useState(null);
  const recRef = useRef(null);
  const endRef = useRef(null);
  const cbRef = useRef(onFinal);
  cbRef.current = onFinal;

  // Stop listening and use what was heard. If the browser does not confirm, finish anyway.
  const stop = useCallback(() => {
    try { recRef.current?.stop(); } catch { /* already stopped */ }
    setTimeout(() => endRef.current?.(), 700);
  }, []);

  const start = useCallback(() => {
    if (!SR) { setError('Voice input needs Chrome, Edge or Safari. You can still type the question.'); return; }
    if (recRef.current) return;
    try { window.speechSynthesis?.cancel(); } catch { /* nothing was being read */ }
    const rec = new SR();
    rec.lang = lang;
    rec.continuous = false;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    let finals = '';
    let heard = '';
    let ended = false;
    let quiet = null;
    setError(null);
    setInterim('');

    // One way out, taken once: by the browser's own end event, by stop(), or by a watchdog.
    const end = () => {
      if (ended) return;
      ended = true;
      clearTimeout(quiet);
      clearTimeout(cap);
      recRef.current = null;
      endRef.current = null;
      setListening(false);
      setInterim('');
      const text = (finals || heard).trim();
      if (text) cbRef.current?.(tidyTranscript(text));
    };
    // A recogniser can stall without ending (no service, a permission prompt left open).
    // Nothing heard in 10 s, or silence for 6 s after words: finish instead of listening for ever.
    const watch = (ms) => {
      clearTimeout(quiet);
      quiet = setTimeout(() => {
        if (!heard) setError(ERRORS['no-speech']);
        try { rec.abort(); } catch { /* gone */ }
        end();
      }, ms);
    };
    const cap = setTimeout(() => { try { rec.stop(); } catch { /* gone */ } setTimeout(end, 700); }, 45000);

    rec.onresult = (e) => {
      let f = '';
      let partial = '';
      for (let i = 0; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) f += r[0].transcript; else partial += r[0].transcript;
      }
      finals = f;
      heard = `${f} ${partial}`.trim();
      setInterim(heard);
      watch(6000);
    };
    rec.onerror = (e) => {
      if (e.error === 'aborted') return;
      setError(ERRORS[e.error] || `Voice input stopped (${e.error}).`);
      if (e.error !== 'no-speech') setTimeout(end, 300);      // most errors are final; do not wait on an end event
    };
    rec.onend = end;
    try {
      rec.start();
      recRef.current = rec;
      endRef.current = end;
      setListening(true);
      watch(10000);
    } catch {
      clearTimeout(cap);
      setError('Voice input could not start. Try again.');
    }
  }, [lang]);

  useEffect(() => () => { endRef.current = null; try { recRef.current?.abort(); } catch { /* gone */ } }, []);

  return { supported: voiceSupported, listening, interim, error, start, stop, clearError: () => setError(null) };
}

// ── Reading answers aloud ────────────────────────────────────────────────
function plain(markdown) {
  return (markdown || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/\|[^\n]*\|/g, ' ')
    .replace(/[*_`#>]/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^\s*[-•]\s+/gm, '')
    .replace(/\b(ENG|JC|FAN|WO|PO|EXQ|TR|FND|DEV|OT|WR|RSQ|THR|FDR|DEP|RSB|JCS)-/g, '$1 ')
    .replace(/\b([TPK])-(\d)/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim();
}

function pickVoice() {
  const voices = window.speechSynthesis.getVoices();
  const english = voices.filter((v) => /^en[-_]/i.test(v.lang));
  return english.find((v) => /natural|neural|google uk english female|samantha|aria|libby|sonia/i.test(v.name))
    || english.find((v) => /en[-_]GB/i.test(v.lang)) || english[0] || null;
}

let speakingId = 0;

/** Read text aloud. Returns a function that stops it. `onEnd` fires when it finishes or is stopped. */
export function speak(markdown, onEnd) {
  if (!speechSupported) { onEnd?.(); return () => {}; }
  const synth = window.speechSynthesis;
  synth.cancel();
  const id = ++speakingId;
  // Long utterances are cut off by some browsers, so read sentence by sentence.
  const sentences = plain(markdown).match(/[^.!?]+[.!?]*/g) || [];
  const voice = pickVoice();
  let ended = false;
  const finish = () => { if (!ended) { ended = true; onEnd?.(); } };
  sentences.map((s) => s.trim()).filter(Boolean).forEach((s, i, all) => {
    const u = new SpeechSynthesisUtterance(s);
    if (voice) u.voice = voice;
    u.lang = voice?.lang || 'en-GB';
    u.rate = 1.03;
    if (i === all.length - 1) u.onend = () => { if (id === speakingId) finish(); };
    u.onerror = () => { if (id === speakingId) finish(); };
    synth.speak(u);
  });
  if (!sentences.length) finish();
  return () => { if (id === speakingId) { synth.cancel(); finish(); } };
}

export function stopSpeaking() {
  speakingId++;
  try { window.speechSynthesis?.cancel(); } catch { /* nothing to stop */ }
}
