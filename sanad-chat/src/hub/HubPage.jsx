// Sanad MRO Intelligence Hub: the chat on the built-in Sanad Digital Assistant.
//
// The design is the Sanad chat (dark panels, light chat elements). What is new here is
// the work: who is asking, the shop time, answers that stream in beside a visual card,
// one-tap next questions, voice in and out, and a notebook of what has been raised.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { SanadMark } from '../ram/Logo';
import Icon from './Icon';
import Card from './Card';
import Markdown from './Markdown';
import { PersonaMenu, ClockMenu, niceTime, holdTime } from './Menus';
import { Notebook, Details, SourceSheet, AccessGate } from './Panels';
import { useVoice, speak, stopSpeaking, speechSupported } from './voice';
import CheckPage from './CheckPage';
import * as api from '../lib/hubApi';
import './hub.css';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
const NEW_TITLE = 'New conversation';
const newChat = () => ({ id: uid(), sessionId: null, title: NEW_TITLE, messages: [], loaded: true });
const store = {
  get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};
const seconds = (ms) => (ms == null ? '' : ms < 950 ? `${Math.max(0.1, ms / 1000).toFixed(1)} s` : `${(ms / 1000).toFixed(1)} s`);

/** Text that catches up with its target a few characters a frame, so answers flow in. */
function useFlowing(target, enabled = true, from = '') {
  const start = !enabled ? target : (from && target.startsWith(from) ? from : '');
  const [shown, setShown] = useState(start);
  const ref = useRef({ shown: start, target });
  ref.current.target = target;
  useEffect(() => {
    if (!enabled) return undefined;
    let raf;
    const tick = () => {
      const s = ref.current;
      if (!s.target.startsWith(s.shown)) s.shown = '';
      if (s.shown.length < s.target.length) {
        const left = s.target.length - s.shown.length;
        s.shown = s.target.slice(0, s.shown.length + Math.max(2, Math.ceil(left / 9)));
        setShown(s.shown);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [enabled]);
  return enabled ? shown : target;
}

const Avatar = () => (
  <div className="hub-bot-avatar"><SanadMark size={18} /></div>
);

function turnsToMessages(turns) {
  const out = [];
  for (const t of turns) {
    out.push({ role: 'user', content: t.content, personaTitle: t.personaTitle, shopTime: t.shopTime, attachmentName: t.attachments?.[0] });
    out.push({ role: 'assistant', turn: t });
  }
  return out;
}

/* ─── One finished answer ─────────────────────────────────────────────── */
function Answer({ turn, fresh, onDetails, onSource, onSave, onOpenNotebook, speakingId, onSpeak }) {
  // `fresh` is set for the answer that has just arrived: { text, cards } is what was already
  // on screen while it streamed, so the text carries on from there and its card does not blink.
  const text = useFlowing(turn.answer || '', !!fresh, fresh?.text || '');
  const onScreen = fresh?.cards || [];
  const [saved, setSaved] = useState(false);
  const typed = !fresh || text.length >= (turn.answer || '').length;
  if (turn.errorText && !turn.answer) {
    return <div className="msg-bot-bubble px-4 py-3 text-[13px]" style={{ color: 'var(--red)' }}>{turn.errorText}</div>;
  }
  const sources = turn.sources || [];
  return (
    <div className="space-y-2.5">
      <div className="msg-bot-bubble px-4 py-3">
        <div className="text-[13.5px]" dir="auto" style={{ color: 'var(--text)' }}><Markdown>{text}</Markdown></div>
        {turn.notice && <div className="hub-notice"><Icon name="alert" size={13} /> {turn.notice}</div>}
      </div>

      {(turn.records || []).map((r) => (
        <button key={r.id} className="hub-record-chip animate-slide-up" onClick={onOpenNotebook} title="Open the notebook">
          <Icon name="clipboard" size={14} />
          <span><b>{r.id}</b> · {r.label}</span>
          <span className="hub-pill tone-warn">{r.status.split(':')[0]}</span>
        </button>
      ))}

      {(turn.cards || []).map((c, i) => ((typed || onScreen.includes(c.id))
        ? <Card key={`${c.id}-${i}`} card={c} still={onScreen.includes(c.id)} /> : null))}

      <div className="hub-answer-foot">
        {sources.filter((s) => s.kind !== 'data').map((s, i) => (
          <button key={i} className="hub-source" disabled={!s.text} onClick={() => s.text && onSource(s)}
            title={s.text ? 'Read the passage' : 'The document this answer rests on'}>
            <Icon name="doc" size={11} /> {s.title}{s.page != null ? `, p. ${s.page}` : ''}
          </button>
        ))}
        <span className="hub-answer-meta">
          {turn.timing?.total_ms != null && <span title="Time to the complete answer">{seconds(turn.timing.total_ms)}</span>}
          {speechSupported && turn.answer && (
            <button className="hub-icon-btn" onClick={() => onSpeak(turn)} title={speakingId === turn.queryId ? 'Stop reading' : 'Read this answer aloud'}>
              <Icon name={speakingId === turn.queryId ? 'stop' : 'speaker'} size={14} />
            </button>
          )}
          <button className="hub-icon-btn" disabled={saved} title={saved ? 'Saved to the notebook' : 'Save this answer to the notebook'}
            onClick={async () => { await onSave(turn); setSaved(true); }}>
            <Icon name={saved ? 'check' : 'bookmark'} size={14} />
          </button>
          <button className="hub-icon-btn" onClick={() => onDetails(turn)} title="How this answer was produced"><Icon name="grid" size={14} /></button>
        </span>
      </div>
    </div>
  );
}

/* ─── The answer while it is being written ────────────────────────────── */
function Live({ live }) {
  const text = useFlowing(live.text || '');
  const steps = live.steps || [];
  return (
    <div className="flex gap-2.5 animate-fade-up">
      <Avatar />
      <div className="hub-answer-col space-y-2.5">
        <div className="msg-bot-bubble px-4 py-3 min-w-[220px]">
          {text
            ? <div className="text-[13.5px] hub-streaming" style={{ color: 'var(--text)' }}><Markdown>{text}</Markdown></div>
            : (
              <div className="space-y-1.5">
                {steps.slice(-5).map((s) => (
                  <div key={s.id} className={`hub-step-line ${s.state === 'running' ? 'is-running' : ''}`}>
                    {s.state === 'running' ? <span className="hub-spinner" /> : <Icon name={s.state === 'error' ? 'x' : 'check'} size={13} />}
                    <span>{s.label}{s.detail ? ` · ${s.detail}` : ''}</span>
                  </div>
                ))}
                {steps.every((s) => s.state !== 'running') && (
                  <div className="hub-step-line is-running"><span className="hub-spinner" /><span>{steps.length ? 'Writing the answer' : 'Reading the question'}</span></div>
                )}
              </div>
            )}
        </div>
        {(live.cards || []).map((c, i) => <Card key={`${c.id}-${i}`} card={c} />)}
      </div>
    </div>
  );
}

/* ─── Model status: shown only when the language model is not answering, with the reason ─── */
function ModelNote({ health, narrow }) {
  const [open, setOpen] = useState(false);
  const missing = !health.llm;
  const failed = health.llm && health.modelCheck?.ok === false;
  if (!missing && !failed) return null;
  const key = health.keyCheck || {};
  return (
    <div className="relative">
      <button className="status-pill" style={{ color: 'var(--amber)', cursor: 'pointer' }} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {missing ? (narrow ? 'No model key' : 'Standard answers only') : 'Model unavailable'}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-50" onClick={() => setOpen(false)} />
          <div className="hub-menu animate-fade-up" style={{ width: 360, padding: 14 }} role="dialog" aria-label="Language model status">
            <div className="hub-menu-item-title" style={{ marginBottom: 6 }}>
              {missing ? 'No language model key is configured' : (health.modelCheck.error || 'The language model is not answering')}
            </div>
            <p className="hub-menu-item-sub" style={{ fontSize: 12 }}>
              Until this is fixed the standard questions are answered straight from the shop data. Free-form questions, what-ifs and actions need the model.
            </p>
            {failed && health.modelCheck.detail && <p className="hub-menu-item-sub" style={{ fontSize: 12, marginTop: 8 }}><b style={{ color: 'var(--text)' }}>The API said:</b> {health.modelCheck.detail}</p>}
            {key.hint && <p className="hub-menu-item-sub" style={{ fontSize: 12, marginTop: 8 }}><b style={{ color: 'var(--text)' }}>What to do:</b> {key.hint}</p>}
            {key.present && (
              <p className="hub-menu-item-sub" style={{ fontSize: 11, marginTop: 8 }}>
                Configured key: {key.kind}, {key.length} characters{key.tidied ? ' (quotes, spaces or a name around it were ignored)' : ''}. The key itself is never shown.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/* ─── The page ────────────────────────────────────────────────────────── */
function Hub({ health, onLocked }) {
  const [config, setConfig] = useState(null);
  const [configError, setConfigError] = useState(null);
  const [persona, setPersona] = useState(() => store.get('sanad_persona', ''));
  const [shopTime, setShopTime] = useState(() => store.get('sanad_shop_time', ''));
  const [chats, setChats] = useState(() => [newChat()]);
  const [activeId, setActiveId] = useState(() => chats[0].id);
  const [live, setLive] = useState(null);                 // the question being answered
  const [input, setInput] = useState('');
  const [attachment, setAttachment] = useState(null);
  const [attaching, setAttaching] = useState(false);
  const [attachError, setAttachError] = useState(null);
  const [notebook, setNotebook] = useState([]);
  const [showNotebook, setShowNotebook] = useState(false);
  const [details, setDetails] = useState(null);
  const [source, setSource] = useState(null);
  const [readAloud, setReadAloud] = useState(() => store.get('sanad_read_aloud', 'off') === 'on');
  const [speakingId, setSpeakingId] = useState(null);
  const [sideOpen, setSideOpen] = useState(false);
  const [menuFor, setMenuFor] = useState(null);
  const [renaming, setRenaming] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [autoSend, setAutoSend] = useState(null);         // { text } while a spoken question waits to be sent
  const [fresh, setFresh] = useState(null);               // the answer that just arrived: { id, text, cards } as last shown live

  const [narrow, setNarrow] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 700px)').matches);
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 700px)');
    const on = () => setNarrow(mq.matches);
    mq.addEventListener?.('change', on);
    return () => mq.removeEventListener?.('change', on);
  }, []);

  const inputRef = useRef(null);
  const scrollRef = useRef(null);
  const contentRef = useRef(null);
  const lastUserRef = useRef(null);
  const followRef = useRef(true);
  const fileRef = useRef(null);
  const liveRef = useRef(null);
  const autoTimer = useRef(null);
  const active = chats.find((c) => c.id === activeId) || chats[0];
  const messages = active?.messages || [];
  const busy = !!live;
  const me = useMemo(() => config?.personas.find((p) => p.key === persona) || config?.personas[0], [config, persona]);

  // ── start-up: configuration, earlier conversations, the notebook ──
  useEffect(() => {
    api.getConfig().then((c) => {
      setConfig(c);
      setPersona((p) => (c.personas.some((x) => x.key === p) ? p : c.defaultPersona));
      setShopTime((t) => (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(t) ? holdTime(t, c.clock) : c.defaultMoment));
    }).catch((e) => { if (e.status !== 401) setConfigError(e.message); });
    api.getSessions().then((sessions) => {
      setChats((prev) => [...prev, ...sessions.map((s) => ({ id: uid(), sessionId: s.id, title: s.title, messages: [], loaded: false, updatedAt: s.updateTimestamp }))]);
    }).catch(() => {});
    api.getNotebook().then(setNotebook).catch(() => {});
    const locked = () => onLocked();
    window.addEventListener('hub:locked', locked);
    return () => window.removeEventListener('hub:locked', locked);
  }, [onLocked]);
  useEffect(() => { if (persona) store.set('sanad_persona', persona); }, [persona]);
  useEffect(() => { if (shopTime) store.set('sanad_shop_time', shopTime); }, [shopTime]);
  useEffect(() => { store.set('sanad_read_aloud', readAloud ? 'on' : 'off'); if (!readAloud) { stopSpeaking(); setSpeakingId(null); } }, [readAloud]);

  // open an earlier conversation: load its turns once
  useEffect(() => {
    if (!active || active.loaded || !active.sessionId) return;
    api.getSessionTurns(active.sessionId)
      .then((turns) => setChats((p) => p.map((c) => (c.id === active.id ? { ...c, loaded: true, messages: turnsToMessages(turns) } : c))))
      .catch(() => setChats((p) => p.map((c) => (c.id === active.id ? { ...c, loaded: true } : c))));
  }, [active]);

  // Scrolling: the latest question is held at the top of the view and its answer fills in
  // below it, so the answer is read from its first line. Scrolling by hand lets go.
  const anchor = useCallback((smooth = true) => {
    const box = scrollRef.current;
    if (!box || !followRef.current) return;
    const max = box.scrollHeight - box.clientHeight;
    const q = lastUserRef.current;
    const top = q ? Math.min(max, Math.max(0, q.offsetTop - 14)) : max;
    if (Math.abs(box.scrollTop - top) > 2) box.scrollTo({ top, behavior: smooth ? 'smooth' : 'auto' });
  }, []);
  useEffect(() => {
    if (!contentRef.current || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(() => anchor());
    ro.observe(contentRef.current);
    return () => ro.disconnect();
  }, [anchor]);
  useEffect(() => { followRef.current = true; setFresh(null); anchor(false); }, [activeId, anchor]);
  useEffect(() => { anchor(); }, [messages.length, anchor]);
  const letGo = () => { followRef.current = false; };
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === '/' && !/^(input|textarea|select)$/i.test(document.activeElement?.tagName || '')) { e.preventDefault(); inputRef.current?.focus(); }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  const patchChat = useCallback((id, fn) => setChats((p) => p.map((c) => (c.id === id ? fn(c) : c))), []);

  const sayAnswer = useCallback((turn) => {
    if (!turn?.answer) return;
    setSpeakingId(turn.queryId);
    speak(turn.answer, () => setSpeakingId((cur) => (cur === turn.queryId ? null : cur)));
  }, []);
  const toggleSpeak = (turn) => {
    if (speakingId === turn.queryId) { stopSpeaking(); setSpeakingId(null); } else sayAnswer(turn);
  };

  // ── ask ──
  const send = useCallback(async (text) => {
    const q = (text ?? input).trim();
    if (!q || liveRef.current) return;
    clearTimeout(autoTimer.current);
    setAutoSend(null);
    stopSpeaking();
    setSpeakingId(null);
    followRef.current = true;
    const chatId = activeId;
    const attached = attachment;
    setInput('');
    setAttachment(null);
    setAttachError(null);
    patchChat(chatId, (c) => ({
      ...c, updatedAt: new Date().toISOString(),
      title: c.title === NEW_TITLE ? (q.length > 44 ? `${q.slice(0, 44)}…` : q) : c.title,
      messages: [...c.messages, { role: 'user', content: q, personaTitle: me?.title, shopTime, attachmentName: attached?.name }],
    }));
    const state = { chatId, queryId: null, text: '', steps: [], cards: [] };
    liveRef.current = state;
    setLive(state);
    try {
      const sessionId = chats.find((c) => c.id === chatId)?.sessionId || null;
      const sub = await api.ask({ content: q, persona, shopTime, querySessionId: sessionId,
        attachments: attached ? [{ name: attached.name, text: attached.text }] : null });
      liveRef.current.queryId = sub.queryId;
      patchChat(chatId, (c) => ({ ...c, sessionId: sub.querySessionId }));
      const deadline = Date.now() + (sub.timeout || 120) * 1000;
      const every = Math.max(150, (sub.pollInterval || 0.3) * 1000);
      let wait = 70;
      let failures = 0;
      let result = null;
      while (!result) {
        await sleep(wait);
        wait = Math.min(every, wait * 1.6);
        let st;
        try { st = await api.getStatus(sub.queryId); failures = 0; } catch (e) {
          // the answer is still being written on the server: ride out a dropped connection (about 25 s)
          if (e.status === 404 || e.status === 401 || e.status === 403 || ++failures >= 15) throw e;
          wait = Math.min(2000, 300 * failures);
          continue;
        }
        if (st.done) { result = st.result; break; }
        liveRef.current = { ...liveRef.current, text: st.text, steps: st.steps, cards: st.cards };
        setLive(liveRef.current);
        if (Date.now() > deadline) throw new Error('The assistant took too long to answer. Please ask again.');
      }
      setFresh({ id: result.queryId, text: liveRef.current?.text || '', cards: (liveRef.current?.cards || []).map((c) => c.id) });
      patchChat(chatId, (c) => ({ ...c, messages: [...c.messages, { role: 'assistant', turn: result }] }));
      if (result.records?.length) api.getNotebook().then(setNotebook).catch(() => {});
      if (readAloud && result.answer && result.state !== 'cancelled') sayAnswer(result);
    } catch (err) {
      patchChat(chatId, (c) => ({ ...c, messages: [...c.messages, { role: 'assistant', error: err.message || 'Something went wrong. Please ask again.' }] }));
    } finally {
      liveRef.current = null;
      setLive(null);
      inputRef.current?.focus();
    }
  }, [input, activeId, attachment, chats, persona, shopTime, me, readAloud, patchChat, sayAnswer]);

  const stop = () => { if (liveRef.current?.queryId) api.cancel(liveRef.current.queryId).catch(() => {}); };

  // ── voice: words appear as they are heard, then the question sends itself ──
  const voice = useVoice({
    onFinal: (text) => {
      setInput(text);
      setAutoSend({ text });
      clearTimeout(autoTimer.current);
      autoTimer.current = setTimeout(() => { setAutoSend(null); send(text); }, 1300);
    },
  });
  const cancelAutoSend = () => { clearTimeout(autoTimer.current); setAutoSend(null); };
  useEffect(() => () => clearTimeout(autoTimer.current), []);
  const toggleMic = () => {
    cancelAutoSend();
    if (voice.listening) voice.stop(); else { stopSpeaking(); setSpeakingId(null); voice.start(); }
  };

  // ── attachments ──
  const pickFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setAttachError(null);
    setAttaching(true);
    try { setAttachment(await api.extractAttachment(file)); } catch (err) { setAttachError(err.message); }
    setAttaching(false);
  };

  // ── conversations ──
  const createChat = () => { const c = newChat(); setChats((p) => [c, ...p]); setActiveId(c.id); setSideOpen(false); inputRef.current?.focus(); };
  const removeChat = (chat) => {
    if (chat.sessionId) api.deleteSession(chat.sessionId).catch(() => {});
    setChats((p) => {
      const rest = p.filter((c) => c.id !== chat.id);
      const next = rest.length ? rest : [newChat()];
      if (!next.some((c) => c.id === activeId)) setActiveId(next[0].id);
      return next;
    });
  };
  const finishRename = (id) => { if (renameValue.trim()) patchChat(id, (c) => ({ ...c, title: renameValue.trim() })); setRenaming(null); };

  const saveAnswer = async (turn) => {
    await api.saveToNotebook({ kind: 'answer', title: turn.content.slice(0, 160), text: turn.answer, persona: turn.persona, shopTime: turn.shopTime, queryId: turn.queryId });
    api.getNotebook().then(setNotebook).catch(() => {});
  };
  const resetDemo = async () => {
    await api.resetAll().catch(() => {});
    const c = newChat();
    setChats([c]);
    setActiveId(c.id);
    setNotebook([]);
    setShowNotebook(false);
  };

  const lastUserIndex = messages.map((m) => m.role).lastIndexOf('user');
  const lastMessage = messages[messages.length - 1];
  const followups = (!busy && lastMessage?.role === 'assistant' && lastMessage.turn?.followups) || [];
  const pending = notebook.filter((r) => r.kind !== 'answer' && r.kind !== 'note').length;
  const heard = voice.listening ? voice.interim : '';

  return (
    <div className="ram-chat hub-chat">
      {/* Recent conversations */}
      {sideOpen && <div className="hub-side-backdrop" onClick={() => setSideOpen(false)} />}
      <div className={`hub-side glass-card flex flex-col ${sideOpen ? 'is-open' : ''}`}>
        <div className="p-4 border-b border-[rgba(255,255,255,0.07)]"><p className="panel-title">Recent conversations</p></div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {chats.map((chat) => (
            <div key={chat.id} className="relative group">
              {renaming === chat.id ? (
                <div className="px-2 py-1.5">
                  <input value={renameValue} onChange={(e) => setRenameValue(e.target.value)} autoFocus
                    onBlur={() => finishRename(chat.id)} onKeyDown={(e) => e.key === 'Enter' && finishRename(chat.id)}
                    className="w-full rounded-lg px-2 py-1.5 text-xs border outline-none"
                    style={{ background: 'rgba(10,32,48,0.5)', borderColor: 'var(--brand-hi)', color: 'var(--text)' }} />
                </div>
              ) : (
                <div className="flex items-center">
                  <button onClick={() => { setActiveId(chat.id); setSideOpen(false); }}
                    className={`flex-1 min-w-0 flex items-center gap-2 px-3 py-2.5 rounded-lg text-xs text-start transition-all chat-item ${chat.id === activeId ? 'active font-semibold' : ''}`}>
                    <span className="truncate flex-1">{chat.title}</span>
                  </button>
                  <button onClick={(e) => { e.stopPropagation(); setMenuFor(menuFor === chat.id ? null : chat.id); }}
                    className="p-1 rounded-md opacity-0 group-hover:opacity-100 focus:opacity-100 hover:bg-[rgba(127,176,220,0.1)] transition-all shrink-0 ms-0.5"
                    style={{ color: 'var(--text-faint)' }} title="Rename or delete">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="12" cy="19" r="1.6" /></svg>
                  </button>
                </div>
              )}
              {menuFor === chat.id && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setMenuFor(null)} />
                  <div className="absolute end-0 top-full mt-0.5 rounded-xl shadow-xl overflow-hidden z-50 min-w-[130px] animate-fade-up"
                    style={{ background: 'rgba(10,32,48,0.96)', border: '1px solid rgba(127,176,220,0.2)' }}>
                    <button onClick={() => { setRenaming(chat.id); setRenameValue(chat.title); setMenuFor(null); }}
                      className="w-full px-3 py-2 text-[11px] text-start hover:bg-[rgba(127,176,220,0.08)]" style={{ color: 'var(--text-md)' }}>Rename</button>
                    <button onClick={() => { removeChat(chat); setMenuFor(null); }}
                      className="w-full px-3 py-2 text-[11px] text-start hover:bg-[var(--red-bg)]" style={{ color: 'var(--red)' }}>Delete</button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
        <div className="p-3 border-t border-[rgba(255,255,255,0.07)]">
          <button onClick={createChat} className="new-chat-btn w-full py-2.5 rounded-lg text-xs font-bold transition-all">+ New conversation</button>
        </div>
      </div>

      {/* Chat */}
      <div className="flex-1 min-w-0 glass-card flex flex-col relative" style={{ boxShadow: 'var(--glass-shadow-lg)' }}>
        <div className="chat-watermark"><SanadMark size={280} /></div>

        <div className="hub-head">
          <button className="hub-icon-btn hub-side-toggle" onClick={() => setSideOpen(true)} title="Conversations"><Icon name="menu" size={17} /></button>
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <span className="w-[3px] h-4 rounded shrink-0" style={{ background: 'var(--brand-grad)' }} />
            <span className="text-sm font-bold truncate" style={{ color: 'var(--text)' }}>{active?.title || NEW_TITLE}</span>
          </div>
          <div className="hub-head-controls">
            <ModelNote health={health} narrow={narrow} />
            {config && <PersonaMenu personas={config.personas} value={persona} onChange={setPersona} />}
            {config && <ClockMenu moments={config.moments} value={shopTime} onChange={setShopTime} clock={config.clock} />}
            {speechSupported && (
              <button className={`hub-control is-compact ${readAloud ? 'is-on' : ''}`} onClick={() => setReadAloud((v) => !v)}
                title={readAloud ? 'Answers are read aloud. Click to turn off.' : 'Read answers aloud'} aria-pressed={readAloud}>
                <Icon name={readAloud ? 'speaker' : 'mute'} size={15} />
                <span className="hub-control-value">Read aloud: {readAloud ? 'on' : 'off'}</span>
              </button>
            )}
            <button className="hub-control is-compact" onClick={() => setShowNotebook(true)} title="Requests, drafts and saved answers">
              <Icon name="book" size={15} />
              <span className="hub-control-value">Notebook</span>
              {notebook.length > 0 && <span className={`hub-count ${pending ? 'is-pending' : ''}`}>{notebook.length}</span>}
            </button>
          </div>
        </div>

        {/* Messages */}
        <div ref={scrollRef} onWheel={letGo} onTouchMove={letGo} className="flex-1 overflow-y-auto px-6 py-5 relative z-[1] hub-scroll">
         <div ref={contentRef} className="space-y-5">
          {configError && <div className="msg-bot-bubble px-4 py-3 text-[13px]" style={{ color: 'var(--red)' }}>The assistant could not start: {configError}</div>}

          {messages.length === 0 && !busy && me && (
            <div className="flex gap-2.5 animate-fade-up">
              <Avatar />
              <div className="hub-answer-col">
                <div className="msg-bot-bubble px-4 py-3 text-[13.5px] leading-[1.7]" style={{ color: 'var(--text)' }}>
                  <b style={{ color: 'var(--brand-lo)' }}>Good day. You are asking as the {me.title}.</b> {me.blurb} Ask in your own words, by typing or by voice.
                  Every answer is grounded in the shop data and approved documents, and decisions remain with authorised personnel.
                </div>
                <div className="hub-suggestions">
                  {me.suggestions.map((s) => (
                    <button key={s.prompt} className="suggestion-chip" onClick={() => send(s.prompt)} title={s.prompt}>
                      <span className="chip-tag">{s.tag}</span>{s.title}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {!active?.loaded && <div className="hub-empty"><span>Loading the conversation…</span></div>}

          {messages.map((msg, i) => (
            msg.role === 'user' ? (
              <div key={i} ref={i === lastUserIndex ? lastUserRef : null} className="flex gap-2.5 flex-row-reverse animate-fade-up">
                <div className="hub-user-avatar">You</div>
                <div className="max-w-[70%]">
                  <div className="msg-user-bubble px-4 py-3 text-[13.5px] leading-[1.7]" dir="auto" style={{ color: 'var(--text)' }}>
                    {msg.attachmentName && <div className="hub-attach-chip"><Icon name="attach" size={11} /> {msg.attachmentName}</div>}
                    {msg.content}
                  </div>
                  {msg.personaTitle && <div className="hub-user-meta">{msg.personaTitle} · shop time {niceTime(msg.shopTime)}</div>}
                </div>
              </div>
            ) : (
              <div key={i} className="flex gap-2.5 animate-fade-up">
                <Avatar />
                <div className="hub-answer-col">
                  {msg.error
                    ? <div className="msg-bot-bubble px-4 py-3 text-[13px]" style={{ color: 'var(--red)' }}>{msg.error}</div>
                    : <Answer turn={msg.turn} fresh={msg.turn.queryId === fresh?.id ? fresh : null}
                        onDetails={setDetails} onSource={setSource} onSave={saveAnswer} onOpenNotebook={() => setShowNotebook(true)}
                        speakingId={speakingId} onSpeak={toggleSpeak} />}
                </div>
              </div>
            )
          ))}

          {live && live.chatId === activeId && <Live live={live} />}
         </div>
        </div>

        {/* Attachment, voice and status lines */}
        {(attachment || attaching || attachError || voice.error || voice.listening || autoSend) && (
          <div className="px-5 pt-1 relative z-[1] flex flex-wrap gap-2 animate-fade-up">
            {voice.listening && (
              <div className="hub-line is-listening"><span className="hub-wave"><i /><i /><i /><i /></span> Listening. Speak your question, then pause.</div>
            )}
            {autoSend && (
              <button className="hub-line is-sending" onClick={() => { cancelAutoSend(); inputRef.current?.focus(); }}>
                <span className="hub-countdown" /> Sending. Tap to edit first.
              </button>
            )}
            {voice.error && <div className="hub-line is-error">{voice.error}<button onClick={voice.clearError}>✕</button></div>}
            {attachError && <div className="hub-line is-error">{attachError}<button onClick={() => setAttachError(null)}>✕</button></div>}
            {attaching && <div className="hub-line"><span className="hub-spinner" /> Reading the document…</div>}
            {attachment && !attaching && (
              <div className="hub-line"><Icon name="attach" size={12} /> <b>{attachment.name}</b>
                <span>{attachment.truncated ? `first ${Math.round(attachment.text.length / 1000)}k characters` : `${(attachment.chars / 1000).toFixed(1)}k characters`}, sent with your next question</span>
                <button onClick={() => setAttachment(null)}>✕</button>
              </div>
            )}
          </div>
        )}

        {/* Next questions, one tap away */}
        {followups.length > 0 && !voice.listening && !autoSend && (
          <div className="hub-dock animate-fade-up">
            <span className="hub-dock-label">Ask next</span>
            {followups.map((f) => (
              <button key={f} className="hub-followup" onClick={() => send(f)}><Icon name="bolt" size={12} /> {f}</button>
            ))}
          </div>
        )}

        {/* Input */}
        <div className="hub-inputwrap px-5 pb-4 pt-2 relative z-[1]">
          <div className={`chat-input flex items-end gap-1.5 px-2 py-1.5 rounded-xl border transition-all ${voice.listening ? 'is-listening' : ''}`}>
            <input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.md,.csv,.json" className="hidden" onChange={pickFile} />
            <button onClick={() => fileRef.current?.click()} disabled={attaching || busy} title="Attach a document to your question"
              className="hub-input-btn"><Icon name="attach" size={16} /></button>
            <textarea ref={inputRef} rows={1} value={voice.listening ? heard : input} readOnly={voice.listening}
              onChange={(e) => { cancelAutoSend(); setInput(e.target.value); }}
              onFocus={() => autoSend && cancelAutoSend()}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder={voice.listening ? 'Listening…' : narrow ? 'Ask a question…' : `Ask the Sanad Digital Assistant${me ? ` as the ${me.title}` : ''}…`}
              maxLength={config?.limits?.questionChars || 4000} dir="auto"
              className="flex-1 bg-transparent border-none outline-none text-[13.5px] py-2 px-2 resize-none leading-relaxed hub-textarea"
              style={{ fontFamily: 'inherit', color: 'var(--text)' }} />
            <button onClick={toggleMic} disabled={busy || !voice.supported} aria-pressed={voice.listening}
              title={!voice.supported ? 'Voice input needs Chrome, Edge or Safari' : voice.listening ? 'Stop listening' : 'Ask by voice'}
              className={`hub-mic ${voice.listening ? 'is-listening' : ''}`}>
              <Icon name={voice.listening ? 'stop' : 'mic'} size={18} />
            </button>
            {busy ? (
              <button onClick={stop} className="hub-send is-stop" title="Stop"><Icon name="stop" size={15} /></button>
            ) : (
              <button onClick={() => send()} disabled={!input.trim() || voice.listening} className="hub-send" title="Send"><Icon name="send" size={15} /></button>
            )}
          </div>
        </div>
      </div>

      {showNotebook && <Notebook items={notebook} onClose={() => setShowNotebook(false)} onReset={resetDemo}
        onRemove={async (id) => { await api.removeFromNotebook(id).catch(() => {}); api.getNotebook().then(setNotebook).catch(() => {}); }} />}
      {details && <Details turn={details} onClose={() => setDetails(null)} />}
      {source && <SourceSheet source={source} onClose={() => setSource(null)} />}
    </div>
  );
}

const CHECK = typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('check');

export default function HubPage({ health: initial }) {
  const [health, setHealth] = useState(initial);
  const [locked, setLocked] = useState(!!initial.locked);
  const lock = useCallback(() => setLocked(true), []);
  // the model's state can change (a key added, an outage): look again now and then
  useEffect(() => {
    const timer = setInterval(() => api.getHealth().then(setHealth).catch(() => {}), 45000);
    return () => clearInterval(timer);
  }, []);
  return (
    <div className="ram-page hub-page h-full">
      {locked
        ? <AccessGate onUnlocked={() => { setLocked(false); api.getHealth().then(setHealth).catch(() => {}); }} />
        : CHECK ? <CheckPage health={health} /> : <Hub health={health} onLocked={lock} />}
    </div>
  );
}
