// SAS Retrieval Agent Manager proxy — every call goes to the FastAPI backend
// under /api/ram (dev: Vite proxies /api to :8000; prod: same origin).
//
// Showcase mode: when no backend answers the health check (a design review on a
// laptop with nothing else running), or when VITE_DEMO=true, every call is
// served by the in-browser showcase in ./demo.js instead, so the whole
// experience — agents, live tool activity, charts, sources, traces — runs
// standalone. The status pill says "Showcase mode" whenever that happens.
import * as demo from './demo';

const API = '/api/ram';
let demoMode = import.meta.env.VITE_DEMO === 'true';
export const isDemo = () => demoMode;

async function req(path, opts = {}) {
  const r = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!r.ok) {
    const e = await r.json().catch(() => ({ detail: 'Connection error' }));
    throw new Error(e.detail || `HTTP ${r.status}`);
  }
  return r.json();
}

// Health decides the mode. A network failure, a dev-proxy error (502/504) or a
// 404 (served by something that is not this backend) all mean "no backend".
// The first check is shared: every other call waits for it, so nothing races
// ahead to a backend that is not there.
async function probeHealth() {
  if (demoMode) return demo.getHealth();
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 6000);
    const r = await fetch(`${API}/health`, { signal: ctrl.signal });
    clearTimeout(timer);
    if (r.status === 404 || r.status >= 500) throw new Error(`HTTP ${r.status}`);
    const ct = r.headers.get('content-type') || '';
    if (!ct.includes('json')) throw new Error('not a backend');
    return await r.json();
  } catch {
    demoMode = true;
    return demo.getHealth();
  }
}
let firstCheck = null;
const modeReady = () => (firstCheck ||= probeHealth());
export const getHealth = async () => {
  if (!firstCheck) return modeReady();
  await firstCheck;
  return probeHealth();
};

export const startDeviceAuth = () => req('/auth/device/start', { method: 'POST' });
export const pollDeviceAuth = () => req('/auth/device/poll', { method: 'POST' });
export const submitViyaCode = (code) =>
  req('/auth/viya/code', { method: 'POST', body: JSON.stringify({ code }) });

// Staying signed in: the backend keeps this browser's RAM session under a
// cookie and refreshes it in the background. After a sign-in it also hands the
// browser a copy of the session; if the backend ever comes back without it
// (a redeploy on a fresh container), the browser hands it back and carries on.
const sessionKey = () => 'sanad_ram_session_v1';
export const saveSession = (s) => { try { if (s) localStorage.setItem(sessionKey(), JSON.stringify(s)); } catch { /* private mode */ } };
export const loadSession = () => { try { const r = localStorage.getItem(sessionKey()); return r ? JSON.parse(r) : null; } catch { return null; } };
export const clearSession = () => { try { localStorage.removeItem(sessionKey()); } catch { /* ignore */ } };
export const restoreSession = (session) =>
  req('/auth/restore', { method: 'POST', body: JSON.stringify({ session }) });
export const signOut = async () => {
  clearSession();
  return req('/auth/signout', { method: 'POST' });
};

// Extract text from an uploaded file (multipart — no JSON headers)
export const extractAttachment = async (file) => {
  await modeReady();
  if (demoMode) return demo.extractAttachment(file);
  const fd = new FormData();
  fd.append('file', file);
  const r = await fetch(`${API}/extract`, { method: 'POST', body: fd });
  if (!r.ok) {
    const e = await r.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(e.detail || `HTTP ${r.status}`);
  }
  return r.json();
};

export const getAgents = async () => { await modeReady(); return demoMode ? demo.getAgents() : req('/agents'); };
export const getCollections = async () => { await modeReady(); return demoMode ? demo.getCollections() : req('/collections'); };
export const getSessions = async () => { await modeReady(); return demoMode ? demo.getSessions() : req('/sessions'); };
export const getSessionQueries = (sessionId) =>
  demoMode ? demo.getSessionQueries(sessionId) : req(`/sessions/${encodeURIComponent(sessionId)}/queries`);
export const deleteSession = (sessionId) =>
  demoMode ? demo.deleteSession(sessionId) : req(`/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });

// target: { type: 'agent', id } or { type: 'collection', id }
// attachments: [{ name, text }] — extracted documents inlined into the query
// Returns { queryId, querySessionId, pollInterval, timeout, result? } —
// poll getQueryStatus until done unless `result` came back inline.
export const submitQuery = (content, target, querySessionId = null, attachments = null, language = 'en') => {
  const body = {
    content,
    agentId: target.type === 'agent' ? target.id : null,
    collectionIds: target.type === 'collection' ? [target.id] : null,
    querySessionId,
    attachments,
    language,
  };
  return demoMode ? demo.submitQuery(body) : req('/query', { method: 'POST', body: JSON.stringify(body) });
};

export const getQueryStatus = (queryId) =>
  demoMode ? demo.getQueryStatus(queryId) : req(`/query/${encodeURIComponent(queryId)}`);

// Tool/LLM/retrieval calls RAM recorded for a query — also works mid-run
export const getQueryTrace = (queryId) =>
  demoMode ? demo.getQueryTrace(queryId) : req(`/query/${encodeURIComponent(queryId)}/trace`);
