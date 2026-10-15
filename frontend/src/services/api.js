const json = async (res) => {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
};

export const getHealth = () => fetch('/api/health').then(json);
export const getScenarios = (persona) => fetch(`/api/scenarios?persona=${persona}`).then(json);
export const getDashboard = (name, filters) => {
  const q = filters && Object.keys(filters).length ? `?filters=${encodeURIComponent(JSON.stringify(filters))}` : '';
  return fetch(`/api/dashboards/${name}${q}`).then(json);
};
export const getQueue = () => fetch('/api/queue').then(json);
export const decideQueue = (id, decision, decidedBy) =>
  fetch(`/api/queue/${id}/${decision}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decided_by: decidedBy }),
  }).then(json);
export const getAudit = () => fetch('/api/audit').then(json);
export const getDocuments = () => fetch('/api/documents').then(json);
export const getDataTables = () => fetch('/api/data/tables').then(json);
export const getDataRows = (table, offset = 0, limit = 50, search = '') =>
  fetch(`/api/data/${table}?offset=${offset}&limit=${limit}&search=${encodeURIComponent(search)}`).then(json);

/**
 * Stream a chat turn. The backend answers NDJSON: {type:"step"...} events while the
 * agents work, then one {type:"final"...} payload. onEvent fires per line.
 */
const STREAM_IDLE_MS = 75000;   // last-resort client guard; the server watchdog fires first

export async function streamChat({ message, sessionId, persona, scenarioId }, onEvent) {
  const ctrl = new AbortController();
  let idle = setTimeout(() => ctrl.abort(), STREAM_IDLE_MS);
  const touch = () => { clearTimeout(idle); idle = setTimeout(() => ctrl.abort(), STREAM_IDLE_MS); };
  let res;
  try {
    res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message, session_id: sessionId, persona, scenario_id: scenarioId || null,
      }),
      signal: ctrl.signal,
    });
  } catch (e) {
    clearTimeout(idle);
    throw new Error(e.name === 'AbortError' ? 'no response from the agent for 75 s, the model may be saturated; try again or use a scenario chip' : e.message);
  }
  if (!res.ok || !res.body) { clearTimeout(idle); throw new Error(`chat failed: ${res.status}`); }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  for (;;) {
    let chunk;
    try { chunk = await reader.read(); } catch (e) {
      clearTimeout(idle);
      throw new Error(e.name === 'AbortError' ? 'the agent went silent for 75 s, the model may be saturated; try again or use a scenario chip' : e.message);
    }
    const { done, value } = chunk;
    if (done) { clearTimeout(idle); break; }
    touch();
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      try { onEvent(JSON.parse(line)); } catch { /* skip malformed line */ }
    }
  }
  if (buf.trim()) {
    try { onEvent(JSON.parse(buf)); } catch { /* ignore */ }
  }
}

export const getStoryHero = () => fetch('/api/story/hero').then(json);
export const getPatient = (id) => fetch(`/api/patient/${id}`).then(json);

export const getModelEval = (t = 0.12) => fetch(`/api/evals/model?threshold=${t}`).then(json);
export const getAgentEval = () => fetch('/api/evals/agent').then(json);
export const runAgentEval = (mode = 'auto') => fetch(`/api/evals/agent/run?mode=${mode}`, { method: 'POST' }).then(json);
export const getAgentEvalStatus = () => fetch('/api/evals/agent/status').then(json);
export const getLlmSelection = () => fetch('/api/evals/llm').then(json);
export const getGovernance = () => fetch('/api/evals/governance').then(json).then((d) => d.controls);

// ── What-if simulator ──
// The Simulator dashboard works on anonymous profiles (clinical archetypes, no identity); the
// patient endpoints remain for the assistant's simulate tool.
export const getSimProfiles = () => fetch('/api/simulate/profiles').then(json);
export const getSimProfile = (id) => fetch(`/api/simulate/profile/${encodeURIComponent(id)}`).then(json);
export const getSimProfilePreset = (id, preset) =>
  fetch(`/api/simulate/profile/${encodeURIComponent(id)}/preset/${preset}`).then(json);
export const getSimPatients = (q = '') => fetch(`/api/simulate/patients?q=${encodeURIComponent(q)}`).then(json);
export const getSimBaseline = (id) => fetch(`/api/simulate/baseline/${encodeURIComponent(id)}`).then(json);
export const getSimPreset = (id, preset) => fetch(`/api/simulate/preset/${encodeURIComponent(id)}/${preset}`).then(json);

/** The subject of a simulation: a profile ({ profileId }) or a patient ({ patientId } or a bare id). */
const simSubject = (who) => (typeof who === 'string' ? { patient_id: who }
  : { profile_id: who?.profileId || undefined, patient_id: who?.patientId || undefined });

export const postSimulate = (who, overrides, signal) =>
  fetch('/api/simulate', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...simSubject(who), overrides }), signal,
  }).then(json);

/** Stream the language-model explanation of a what-if: NDJSON {type:meta|token|final}. */
export async function streamExplain({ patientId, profileId, overrides, actor }, onEvent, signal) {
  const res = await fetch('/api/simulate/explain', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...simSubject({ patientId, profileId }), overrides, actor: actor || 'clinician' }), signal,
  });
  if (!res.ok || !res.body) throw new Error(`explain failed: ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      try { onEvent(JSON.parse(line)); } catch { /* partial line */ }
    }
  }
  if (buf.trim()) { try { onEvent(JSON.parse(buf)); } catch { /* ignore */ } }
}

// ── Environment links (SAS Viya, SAS RAM, materials) from the server's env ──
export const getLinks = () => fetch('/api/links').then(json);

// ── Teams: one SAS Viya + SAS RAM pair per team; the team signs in once per browser (a cookie) ──
export const getTeams = () => fetch('/api/teams').then(json);
export const loginTeam = async (username, password) => {
  const r = await fetch('/api/teams/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${r.status}`); }
  return r.json();
};
export const logoutTeam = () => fetch('/api/teams/logout', { method: 'POST' }).then(json);

// ── Cancer screening: colorectal screening, the composite AI example ──
const CRC = '/api/screening/crc';
export const getCrcRules = () => fetch(`${CRC}/rules`).then(json);
export const getCrcDecisionCases = () => fetch(`${CRC}/rules/test_cases`).then(json);
export const runCrcDecision = (personId) => fetch(`${CRC}/rules/run/${encodeURIComponent(personId)}`).then(json);
export const getCrcDashboard = (filters) => {
  const q = filters && Object.keys(filters).length ? `?filters=${encodeURIComponent(JSON.stringify(filters))}` : '';
  return fetch(`${CRC}/dashboard${q}`).then(json);
};
export const getCrcMap = () => fetch(`${CRC}/map`).then(json);
export const getCrcWorklist = (kind = 'due', limit = 25, uninvitedOnly = false) =>
  fetch(`${CRC}/worklist?kind=${kind}&limit=${limit}&uninvited_only=${uninvitedOnly}`).then(json);
export const getCrcPerson = (id) => fetch(`${CRC}/person/${encodeURIComponent(id)}`).then(json);
export const getCrcDataTables = () => fetch(`${CRC}/data/tables`).then(json);
export const getCrcDataRows = (table, offset = 0, limit = 50, search = '') =>
  fetch(`${CRC}/data/${table}?offset=${offset}&limit=${limit}&search=${encodeURIComponent(search)}`).then(json);
export const getCrcDocuments = () => fetch(`${CRC}/documents`).then(json);
export const getCrcModel = () => fetch(`${CRC}/model`).then(json);
export const getCrcProfiles = () => fetch(`${CRC}/model/profiles`).then(json);
export const getCrcProfile = (id) => fetch(`${CRC}/model/profile/${encodeURIComponent(id)}`).then(json);
export const getCrcProfilePreset = (id, preset) => fetch(`${CRC}/model/profile/${encodeURIComponent(id)}/preset/${preset}`).then(json);
export const postCrcSimulate = (profileId, overrides, signal) =>
  fetch(`${CRC}/model/simulate`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_id: profileId, overrides }), signal }).then(json);
export const getCrcScenarios = () => fetch(`${CRC}/agent/scenarios`).then(json);
export const getCrcQueue = () => fetch(`${CRC}/agent/queue`).then(json);
export const getCrcAudit = () => fetch(`${CRC}/agent/audit`).then(json);

/** NDJSON reader shared by the Cancer screening streams: {type: meta|token|final} or {type: step|final}. */
async function readNdjson(res, onEvent) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      try { onEvent(JSON.parse(line)); } catch { /* partial line */ }
    }
  }
  if (buf.trim()) { try { onEvent(JSON.parse(buf)); } catch { /* ignore */ } }
}
export async function streamCrcExplain({ profileId, overrides }, onEvent, signal) {
  const res = await fetch(`${CRC}/model/explain`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_id: profileId, overrides }), signal });
  if (!res.ok || !res.body) throw new Error(`explain failed: ${res.status}`);
  await readNdjson(res, onEvent);
}
export async function streamCrcAgent({ message, sessionId, scenarioId }, onEvent, signal) {
  const res = await fetch(`${CRC}/agent/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId, scenario_id: scenarioId || null }), signal });
  if (!res.ok || !res.body) throw new Error(`agent failed: ${res.status}`);
  await readNdjson(res, onEvent);
}

// ── Cancer screening: the screening check ──
export const getCrcOptions = () => fetch('/api/screening/crc/options').then(json);
export const assessCrc = (body) =>
  fetch('/api/screening/crc/assess', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(json);
export async function streamCrcChat({ person, messages }, onEvent, signal) {
  const res = await fetch('/api/screening/crc/chat', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ person, messages }), signal,
  });
  if (!res.ok || !res.body) throw new Error(`chat failed: ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      try { onEvent(JSON.parse(line)); } catch { /* partial line */ }
    }
  }
  if (buf.trim()) { try { onEvent(JSON.parse(buf)); } catch { /* ignore */ } }
}

// ── The Design Thinking Agent (the scripted Population Health Builder) ──
export async function streamDesignChat({ sessionId, message }, onEvent, signal) {
  const res = await fetch('/api/design/chat', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }), signal,
  });
  if (!res.ok || !res.body) throw new Error(`design chat failed: ${res.status}`);
  await readNdjson(res, onEvent);
}
export const getDesignState = (sessionId) => fetch(`/api/design/state?session_id=${encodeURIComponent(sessionId)}`).then(json);
export const resetDesign = (sessionId) =>
  fetch('/api/design/reset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: sessionId }) }).then(json);
