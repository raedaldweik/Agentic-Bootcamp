import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { getTeams, loginTeam, logoutTeam } from '../services/api';
import { setSessionScope } from '../ram/api';

export const PERSONAS = {
  executive: {
    id: 'executive', name: 'Population Health Executive', sub: 'Emirates Health Services',
    avatar: 'You', color: 'bg-[#2B5378]',
    welcome: "Welcome. Ask about registry outcomes, care gaps, cost, equity or demand, or run one of the scenarios below. Every figure is computed from the registry and every clinical statement is cited to a guideline page.",
  },
};

const NEW_TITLE = 'New conversation';
const STORE_KEY = 'bootcamp_chats_v1';
const genId = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

const welcomeMsg = (persona) => ({ role: 'assistant', welcome: true, content: PERSONAS[persona].welcome });
const freshChat = (persona) => ({
  id: genId(), title: NEW_TITLE, persona, messages: [welcomeMsg(persona)],
});

function loadStored() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORE_KEY) || 'null');
    if (Array.isArray(raw?.chats) && raw.chats.length) return raw;
  } catch { /* private mode / corrupt */ }
  return null;
}

const Ctx = createContext(null);

export function AppProvider({ children }) {
  const stored = loadStored();
  const [persona, setPersona] = useState('executive');
  // Teams: which SAS Viya + SAS RAM pair this browser uses. A team signs in once (a
  // cookie); `teamsEnabled` is false when the deployment runs one environment for
  // everyone, and then there is no sign-in at all.
  const [teamsEnabled, setTeamsEnabled] = useState(false);
  const [team, setTeam] = useState(null);           // {id, name, username} or null
  const [teamsLoaded, setTeamsLoaded] = useState(false);
  useEffect(() => {
    getTeams().then((r) => {
      setTeamsEnabled(!!r?.enabled);
      setTeam(r?.current || null);
      setSessionScope(r?.current?.id || null);
    }).catch(() => {}).finally(() => setTeamsLoaded(true));
  }, []);
  // The sign-in card stays up until this browser has signed in as a team. The cookie
  // keeps the sign-in across refreshes; "switch" in the header brings the card back.
  const gateOpen = teamsLoaded && teamsEnabled && !team;
  const signInTeam = useCallback(async (username, password) => {
    const r = await loginTeam(username, password);
    setTeam(r.current);
    setSessionScope(r.current?.id || null);
    return r.current;
  }, []);
  const signOutTeam = useCallback(async () => {
    try { await logoutTeam(); } catch { /* the cookie is gone either way on the next load */ }
    setTeam(null);
    setSessionScope(null);
  }, []);
  // Dashboard cross-filter: {tier: 'High', facility: '...'}; shared by every dashboard tab.
  const [dashFilter, setDashFilter] = useState({});
  const toggleFilter = useCallback((key, value) => setDashFilter((f) => {
    if (value == null || f[key] === value) { const { [key]: _drop, ...rest } = f; return rest; }
    return { ...f, [key]: value };
  }), []);
  const clearFilter = useCallback(() => setDashFilter({}), []);
  const [chats, setChats] = useState(stored?.chats || [freshChat('executive')]);
  const [activeChatId, setActiveChatId] = useState(stored?.activeChatId || (stored?.chats?.[0]?.id) || null);

  const visibleChats = chats.filter((c) => c.persona === persona);
  const activeChat = chats.find((c) => c.id === activeChatId && c.persona === persona)
    || visibleChats[0] || null;

  // Keep an active chat valid for the current persona (create one if none exists)
  useEffect(() => {
    if (!activeChat) {
      const c = freshChat(persona);
      setChats((p) => [c, ...p]);
      setActiveChatId(c.id);
    } else if (activeChat.id !== activeChatId) {
      setActiveChatId(activeChat.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persona, activeChat?.id]);

  // Persist (cap at 20 conversations; survive quota errors silently)
  useEffect(() => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({ persona, activeChatId, chats: chats.slice(0, 20) }));
    } catch { /* quota / private mode */ }
  }, [chats, persona, activeChatId]);

  const createNewChat = useCallback(() => {
    const c = freshChat(persona);
    setChats((p) => [c, ...p]);
    setActiveChatId(c.id);
  }, [persona]);

  const addMessage = useCallback((chatId, msg) => {
    setChats((p) => p.map((c) => {
      if (c.id !== chatId) return c;
      const updated = { ...c, messages: [...c.messages, msg] };
      if (msg.role === 'user' && c.title === NEW_TITLE) {
        updated.title = msg.content.slice(0, 42) + (msg.content.length > 42 ? '…' : '');
      }
      return updated;
    }));
  }, []);

  const renameChat = useCallback((chatId, title) => {
    setChats((p) => p.map((c) => (c.id === chatId ? { ...c, title } : c)));
  }, []);

  const deleteChat = useCallback((chatId) => {
    setChats((p) => {
      const filtered = p.filter((c) => c.id !== chatId);
      const forPersona = filtered.filter((c) => c.persona === persona);
      const next = forPersona.length === 0 ? [freshChat(persona), ...filtered] : filtered;
      setActiveChatId((curr) => {
        const stillVisible = next.some((c) => c.id === curr && c.persona === persona);
        return stillVisible ? curr : next.find((c) => c.persona === persona).id;
      });
      return next;
    });
  }, [persona]);

  return (
    <Ctx.Provider value={{ teamsEnabled, team, teamsLoaded, signInTeam, signOutTeam, gateOpen,
      persona, setPersona, personaInfo: PERSONAS[persona],
      chats: visibleChats, activeChat, activeChatId: activeChat?.id,
      setActiveChatId, createNewChat, addMessage, renameChat, deleteChat,
      dashFilter, toggleFilter, clearFilter,
    }}>
      {children}
    </Ctx.Provider>
  );
}

export const useApp = () => useContext(Ctx);
