import { useState, useRef, useEffect, useCallback } from 'react';
import { useStrings } from './lib/strings';
import { ChatProvider, useChat } from './lib/ChatContext';
import {
  getHealth, getAgents, getCollections, submitQuery, getQueryStatus, getQueryTrace, extractAttachment,
  loadSession, saveSession, clearSession, restoreSession, signOut, isDemo,
} from './lib/api';
import Background from './components/Background';
import Sidebar from './components/Sidebar';
import TopBar from './components/TopBar';
import MessageList from './components/MessageList';
import Composer from './components/Composer';
import QueryDetails from './components/QueryDetails';
import SourceViewer from './components/SourceViewer';
import SignIn from './components/SignIn';

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

/* ─── Connection card (rail footer): health · sign-in · sign-out ──────── */
function useHealth() {
  const [health, setHealth] = useState(null);
  const check = useCallback(async () => {
    let h;
    try { h = await getHealth(); } catch { setHealth({ status: 'down' }); return; }
    if (h.status === 'signin_required') {
      const saved = loadSession();
      if (saved) {
        try {
          const r = await restoreSession(saved);
          if (r.ok) { saveSession(r.session); window.location.reload(); return; }
        } catch { clearSession(); }
      }
    }
    setHealth(h);
  }, []);
  useEffect(() => {
    check();
    const timer = setInterval(check, 60000);
    window.addEventListener('ram:signin-required', check);
    return () => { clearInterval(timer); window.removeEventListener('ram:signin-required', check); };
  }, [check]);
  return health;
}

function ConnectionCard({ health }) {
  const { t } = useStrings();
  const ok = health?.status === 'ok';
  const needsSignin = health?.status === 'signin_required';
  const canSignOut = ok && health?.mode === 'live' && health?.auth === 'device';
  const [signingOut, setSigningOut] = useState(false);
  const doSignOut = async () => {
    if (signingOut) return;
    setSigningOut(true);
    try { await signOut(); } catch { /* the local copy is gone either way */ }
    window.location.reload();
  };
  const label = health == null ? t('connecting')
    : health.mode === 'demo' ? t('demoMode')
    : health.mode === 'mock' ? t('mockMode')
    : ok ? t('connected')
    : needsSignin ? t('signInRequired')
    : health.status === 'unconfigured' ? t('notConfigured')
    : t('backendOffline');
  const tone = ok ? 'ok' : needsSignin ? 'warn' : health ? 'err' : 'warn';
  const sub = health?.mode === 'demo' ? t('demoHint') : health?.ramUrl || t('system');

  return (
    <div className="sn-status-card">
      <span className={`sn-dot ${tone} ${ok ? '' : 'pulse'}`} />
      <span className="label" title={sub}>{label}<span className="sub">{sub}</span></span>
      {needsSignin && <SignIn health={health} />}
      {canSignOut && <button onClick={doSignOut} disabled={signingOut} className="sn-btn sn-btn-ghost" title={t('signOutTitle')}>{signingOut ? '…' : t('signOut')}</button>}
    </div>
  );
}

/* ─── The chat ─────────────────────────────────────────────────────────── */
function ChatView() {
  const { t } = useStrings();
  const { chats, activeChat, activeChatId, setActiveChatId, addMessage, setChatSession, renameChat, deleteChat, createNewChat, NEW_TITLE } = useChat();
  const messages = activeChat?.messages || [];
  const health = useHealth();

  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem('sanad-rail') === 'collapsed'; } catch { return false; } });
  useEffect(() => { try { localStorage.setItem('sanad-rail', collapsed ? 'collapsed' : 'open'); } catch { /* ignore */ } }, [collapsed]);

  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [liveTrace, setLiveTrace] = useState(null);
  const [details, setDetails] = useState(null);
  const [source, setSource] = useState(null);

  const [agents, setAgents] = useState([]);
  const [collections, setCollections] = useState([]);
  const [target, setTarget] = useState(null);
  const [targetsLoading, setTargetsLoading] = useState(true);
  const [targetsError, setTargetsError] = useState(null);

  const [attachment, setAttachment] = useState(null);
  const [attaching, setAttaching] = useState(false);
  const [attachError, setAttachError] = useState(null);

  const inputRef = useRef(null);
  const endRef = useRef(null);

  // Agents / collections — loaded once the health check has settled the mode
  useEffect(() => {
    if (health == null) return;
    let cancelled = false;
    Promise.allSettled([getAgents(), getCollections()]).then(([a, c]) => {
      if (cancelled) return;
      const agentList = a.status === 'fulfilled' ? a.value : [];
      const collList = c.status === 'fulfilled' ? c.value : [];
      setAgents(agentList);
      setCollections(collList);
      if (a.status === 'rejected' && c.status === 'rejected') {
        setTargetsError(a.reason?.message || 'Could not reach RAM');
      } else if (agentList.length > 0) {
        setTarget(prev => prev || { type: 'agent', id: agentList[0].id, name: agentList[0].name });
      } else if (collList.length > 0) {
        setTarget(prev => prev || { type: 'collection', id: collList[0].id, name: collList[0].name });
      }
      setTargetsLoading(false);
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [health == null, health?.status, health?.mode]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, loading, liveTrace]);

  // "/" focuses the composer from anywhere; Escape closes overlays
  useEffect(() => {
    const onKey = (e) => {
      const tag = document.activeElement?.tagName;
      if (e.key === '/' && tag !== 'TEXTAREA' && tag !== 'INPUT') { e.preventDefault(); inputRef.current?.focus(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const pickFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setAttachError(null);
    setAttaching(true);
    try { setAttachment(await extractAttachment(file)); }
    catch (err) { setAttachError(err.message); }
    setAttaching(false);
  };

  const send = async (text) => {
    const q = (typeof text === 'string' ? text : input).trim();
    if (!q || loading) return;
    if (!target) {
      addMessage(activeChatId, { role: 'assistant', type: 'text', content: t('selectAgentFirst'), isError: true });
      return;
    }
    setInput('');
    if (inputRef.current) inputRef.current.style.height = 'auto';
    const attached = attachment;
    setAttachment(null);
    setAttachError(null);
    addMessage(activeChatId, { role: 'user', type: 'text', content: q, attachmentName: attached?.name });
    setLoading(true);
    setLiveTrace(null);
    try {
      const sub = await submitQuery(q, target, activeChat?.sessionId || null,
        attached ? [{ name: attached.name, text: attached.text }] : null);
      if (sub.querySessionId) setChatSession(activeChatId, sub.querySessionId, target);

      let res = sub.result;
      if (!res) {
        const interval = Math.max((sub.pollInterval || 2) * 1000, 1000);
        const deadline = Date.now() + (sub.timeout || 600) * 1000;
        let consecutiveErrors = 0;
        let tick = 0;
        for (;;) {
          await sleep(Math.min(interval, 1000));
          if (tick++ % 2 === 0) getQueryTrace(sub.queryId).then(setLiveTrace).catch(() => {});
          let st;
          try {
            st = await getQueryStatus(sub.queryId);
            consecutiveErrors = 0;
          } catch (e) {
            if (++consecutiveErrors >= 5) throw e;
            if (Date.now() >= deadline) throw new Error(t('agentTimeout', { n: sub.timeout || 600 }));
            continue;
          }
          if (st.done) { res = st.result; break; }
          if (Date.now() >= deadline) throw new Error(t('agentTimeout', { n: sub.timeout || 600 }));
        }
      }

      if (res.errorCode && res.errorCode !== 0) {
        addMessage(activeChatId, { role: 'assistant', type: 'text', content: `${t('agentErrorPrefix')} ${res.errorText || 'query failed'}`, isError: true });
      } else {
        let trace = null;
        try { trace = await getQueryTrace(res.queryId || sub.queryId); } catch { /* best-effort */ }
        addMessage(activeChatId, { role: 'assistant', type: 'structured', data: trace ? { ...res, trace } : res, query: q });
      }
    } catch (err) {
      addMessage(activeChatId, { role: 'assistant', type: 'text', content: `${t('errorPrefix')} ${err.message}`, isError: true });
      if (/not signed in/i.test(err.message)) window.dispatchEvent(new Event('ram:signin-required'));
    }
    setLoading(false);
    setLiveTrace(null);
    inputRef.current?.focus();
  };

  // Scope the conversation list to the selected agent/collection. Untagged
  // chats (brand-new local ones) stay visible everywhere.
  const visibleChats = chats.filter(chat => {
    if (!target) return true;
    const tagged = chat.agentId || (chat.collectionIds && chat.collectionIds.length > 0);
    if (!tagged) return true;
    return target.type === 'agent' ? chat.agentId === target.id : (chat.collectionIds || []).includes(target.id);
  });
  useEffect(() => {
    if (!target || visibleChats.some(c => c.id === activeChatId)) return;
    if (visibleChats.length > 0) setActiveChatId(visibleChats[0].id);
    else createNewChat();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  const title = (activeChat?.title && activeChat.title !== NEW_TITLE) ? activeChat.title : t('newConversationTitle');

  return (
    <div className="sn-app" lang="en">
      <Background />
      <div className="sn-layout">
        <Sidebar chats={visibleChats} activeChatId={activeChatId} setActiveChatId={setActiveChatId}
          createNewChat={createNewChat} renameChat={renameChat} deleteChat={deleteChat}
          collapsed={collapsed} onToggle={() => setCollapsed(c => !c)}
          footer={<ConnectionCard health={health} />} />

        <main className="sn-main sn-glass">
          <TopBar title={title} demo={isDemo()}
            targetProps={{ agents, collections, target, onChange: setTarget, loading: targetsLoading, error: targetsError }} />
          <MessageList messages={messages} loading={loading} liveTrace={liveTrace} target={target}
            onSuggest={(p) => send(p)} onOpenSource={setSource} onOpenDetails={setDetails} endRef={endRef} />
          <Composer input={input} setInput={setInput} onSend={send} loading={loading} target={target} inputRef={inputRef}
            attachment={attachment} attaching={attaching} attachError={attachError}
            onPickFile={pickFile} onClearAttachment={() => setAttachment(null)} onClearError={() => setAttachError(null)} />
        </main>
      </div>

      {details && <QueryDetails data={details.data} query={details.query} onClose={() => setDetails(null)} onOpenSource={setSource} />}
      {source && <SourceViewer source={source} onClose={() => setSource(null)} />}
    </div>
  );
}

/** Sanad AI — a standalone chat on SAS Retrieval Agent Manager (via /api/ram). */
export default function App() {
  return (
    <ChatProvider>
      <ChatView />
    </ChatProvider>
  );
}
