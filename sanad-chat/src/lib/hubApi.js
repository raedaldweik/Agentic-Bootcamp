// The Sanad Digital Assistant API (/api/assistant): the built-in assistant.
// A question is submitted, then polled; each poll returns the answer as far as it has
// been written, the steps so far and the card.

const API = '/api/assistant';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function req(path, opts = {}) {
  let r;
  try {
    r = await fetch(`${API}${path}`, { headers: { 'Content-Type': 'application/json' }, ...opts });
  } catch {
    throw new Error('The connection dropped. Check the network and try again.');
  }
  if (!r.ok) {
    const e = await r.json().catch(() => ({ detail: 'Connection error' }));
    if (r.status === 401 && e.detail === 'access_code_required') window.dispatchEvent(new Event('hub:locked'));
    const err = new Error(typeof e.detail === 'string' ? e.detail : `HTTP ${r.status}`);
    err.status = r.status;
    throw err;
  }
  return r.json();
}

/**
 * Which assistant this server offers.
 *   { kind: 'hub', health }   the built-in Sanad Digital Assistant
 *   { kind: 'ram' }           this server does not serve it: the chat runs on SAS RAM (or its showcase)
 *   { kind: 'down' }          the server could not be reached: it is starting, restarting or offline
 * A server that is briefly unreachable is asked again before anything is decided, so a restart
 * never shows someone a different application.
 */
export async function detect() {
  if (import.meta.env.VITE_DEMO === 'true') return { kind: 'ram' };
  const tries = import.meta.env.DEV ? 1 : 4;
  for (let attempt = 0; attempt < tries; attempt++) {
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 7000);
      const r = await fetch(`${API}/health`, { signal: ctrl.signal, cache: 'no-store' });
      clearTimeout(timer);
      const json = (r.headers.get('content-type') || '').includes('json');
      if (r.ok && json) {
        const health = await r.json();
        return health.mode === 'builtin' ? { kind: 'hub', health } : { kind: 'ram' };
      }
      if (r.status === 404 || (r.ok && !json)) return { kind: 'ram' };   // answered, and it is not there
    } catch { /* no answer: try again */ }
    if (attempt < tries - 1) await sleep(700 * (attempt + 1));
  }
  return import.meta.env.DEV ? { kind: 'ram' } : { kind: 'down' };
}

export const getHealth = () => req('/health');
export const unlock = (code) => req('/unlock', { method: 'POST', body: JSON.stringify({ code }) });
export const getConfig = () => req('/config');
export const getSessions = () => req('/sessions');
export const getSessionTurns = (id) => req(`/sessions/${encodeURIComponent(id)}/queries`);
export const deleteSession = (id) => req(`/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' });
export const ask = (body) => req('/query', { method: 'POST', body: JSON.stringify(body) });
export const getStatus = (id) => req(`/query/${encodeURIComponent(id)}`);
export const cancel = (id) => req(`/query/${encodeURIComponent(id)}/cancel`, { method: 'POST' });
export const getTrace = (id) => req(`/query/${encodeURIComponent(id)}/trace`);
export const getNotebook = () => req('/notebook');
export const saveToNotebook = (body) => req('/notebook', { method: 'POST', body: JSON.stringify(body) });
export const removeFromNotebook = (id) => req(`/notebook/${encodeURIComponent(id)}`, { method: 'DELETE' });
export const resetAll = () => req('/reset', { method: 'POST' });

export async function extractAttachment(file) {
  const fd = new FormData();
  fd.append('file', file);
  const r = await fetch(`${API}/extract`, { method: 'POST', body: fd });
  if (!r.ok) {
    const e = await r.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(e.detail || `HTTP ${r.status}`);
  }
  return r.json();
}
