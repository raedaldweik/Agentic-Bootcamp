// The Sanad Digital Assistant API (/api/assistant): the built-in assistant.
// A question is submitted, then polled; each poll returns the answer as far as it has
// been written, the steps so far and the card.

const API = '/api/assistant';

async function req(path, opts = {}) {
  const r = await fetch(`${API}${path}`, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!r.ok) {
    const e = await r.json().catch(() => ({ detail: 'Connection error' }));
    if (r.status === 401 && e.detail === 'access_code_required') window.dispatchEvent(new Event('hub:locked'));
    const err = new Error(typeof e.detail === 'string' ? e.detail : `HTTP ${r.status}`);
    err.status = r.status;
    throw err;
  }
  return r.json();
}

/** The built-in assistant's health, or null when this backend does not serve it. */
export async function detect() {
  if (import.meta.env.VITE_DEMO === 'true') return null;
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 6000);
    const r = await fetch(`${API}/health`, { signal: ctrl.signal });
    clearTimeout(timer);
    if (!r.ok || !(r.headers.get('content-type') || '').includes('json')) return null;
    const h = await r.json();
    return h.mode === 'builtin' ? h : null;
  } catch {
    return null;
  }
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
