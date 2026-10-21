// In-browser showcase of the RAM contract — used when no backend is reachable
// (see api.js). Flavoured for Sanad: engine MRO shop visits, induction
// capacity, the leasing book and the maintenance document collections. Every
// figure is synthetic and every answer says so. The shapes mirror what the
// FastAPI backend returns from a live SAS Retrieval Agent Manager, including a
// trace that fills in step by step while a query "runs", so the live activity
// timeline and the flight recorder behave exactly as they do against RAM.

const uuid = () => (crypto.randomUUID ? crypto.randomUUID()
  : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
      const r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    }));
const now = () => new Date().toISOString();
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const AGENTS = [
  { id: 'a1000000-0000-0000-0000-000000000001', name: 'Aerotech MRO Agent',
    description: 'Engine shop visits, turnaround, induction capacity, workscope status' },
  { id: 'a1000000-0000-0000-0000-000000000002', name: 'Capital Leasing Agent',
    description: 'Lease book, exposure by lessee and region, remarketing pipeline' },
  { id: 'a1000000-0000-0000-0000-000000000003', name: 'Powertech Agent',
    description: 'Industrial gas-turbine MRO: outages, parts, field service' },
];
const COLLECTIONS = [
  { id: 'c1000000-0000-0000-0000-000000000001', name: 'Engine Maintenance Manuals',
    description: 'OEM engine manuals, service bulletins and workscope planning guides (PDF).' },
  { id: 'c1000000-0000-0000-0000-000000000002', name: 'Policies & SOPs',
    description: 'Shop procedures, quality and safety standards, inspection intervals.' },
];

const CONTEXT = {
  sop: [{
    pageContent: '7.4 Post-repair inspection. After any hot-section repair the engine shall receive a borescope inspection of the HPT stage-1 nozzle guide vanes and blades before release, and again at the first 250 cycles in service. Where blade coating loss above 15% of the airfoil area is found, the inspection interval reverts to 100 cycles until two consecutive clean inspections are recorded. Record every inspection in the shop-visit file and the fleet health dashboard.',
    metadata: { filename: 'SOP-QA-017_Borescope_Inspection_Intervals.pdf', page: 12 },
  }, {
    pageContent: 'Table 3 — Inspection intervals by repair class. Class A (cold section): 500 cycles. Class B (hot section, no coating work): 250 cycles. Class C (hot section with coating restoration): 250 cycles, then 100 cycles where coating loss is found above threshold.',
    metadata: { filename: 'SOP-QA-017_Borescope_Inspection_Intervals.pdf', page: 14 },
  }],
  mro: [{
    pageContent: 'Shop-visit turnaround (TAT) is measured from engine induction to test-cell release, excluding customer-induced holds. The 2026 target is 62 days for performance restorations and 48 days for hospital visits. TAT above 70 days triggers a workscope review with the customer programme manager.',
    metadata: { filename: 'Sanad_Aerotech_Shop_Performance_Standard_2026.pdf', page: 4 },
  }],
  lease: [{
    pageContent: 'Portfolio concentration limits. No single lessee may exceed 15% of net book value and no single region 45%. Exposure is reported quarterly by region, lessee credit tier and asset type, with remarketing status for every asset within 18 months of lease expiry.',
    metadata: { filename: 'Sanad_Capital_Portfolio_Policy.pdf', page: 9 },
  }],
};

const MONTHS = ['Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct'];

const CHARTS = {
  tat: {
    kind: 'chart', type: 'line',
    title: 'Shop-visit turnaround — days from induction to test-cell release',
    subtitle: 'Rolling 12 months · performance restorations vs hospital visits',
    data: MONTHS.map((m, i) => ({
      month: m,
      restoration: [71, 69, 68, 66, 64, 65, 63, 61, 60, 59, 58, 57][i],
      hospital: [52, 50, 49, 51, 48, 47, 47, 46, 45, 44, 45, 43][i],
    })),
    xKey: 'month',
    yKeys: [{ key: 'restoration', label: 'Performance restoration' }, { key: 'hospital', label: 'Hospital visit' }],
  },
  inductions: {
    kind: 'chart', type: 'bar',
    title: 'Inductions by engine type — this quarter vs slot capacity',
    data: [
      { engine: 'GEnx-1B', inducted: 11, capacity: 12 },
      { engine: 'Trent 700', inducted: 9, capacity: 10 },
      { engine: 'V2500-A5', inducted: 14, capacity: 14 },
      { engine: 'GE90-115B', inducted: 6, capacity: 8 },
      { engine: 'CFM56-5B', inducted: 12, capacity: 12 },
      { engine: 'LEAP-1A', inducted: 7, capacity: 10 },
    ],
    xKey: 'engine',
    yKeys: [{ key: 'inducted', label: 'Inducted' }, { key: 'capacity', label: 'Slot capacity' }],
  },
  exposure: {
    kind: 'chart', type: 'pie',
    title: 'Leasing portfolio exposure by region — % of net book value',
    data: [
      { region: 'Middle East', share: 38 },
      { region: 'Europe', share: 24 },
      { region: 'Asia-Pacific', share: 19 },
      { region: 'Americas', share: 12 },
      { region: 'Africa', share: 7 },
    ],
    xKey: 'region',
    yKeys: [{ key: 'share', label: '% of NBV' }],
  },
};

const DISCLAIMER = '\n\n_Showcase answer — synthetic figures for the design preview. Point the app at a live SAS Retrieval Agent Manager for real data._';

// Pick the scripted answer that best fits the question.
function script(content, agentName) {
  const q = content.toLowerCase();
  if (/turnaround|tat|trend|last 12|month/.test(q)) {
    return {
      answer: `**Shop-visit turnaround is improving.** Over the rolling 12 months, performance-restoration TAT fell from **71 to 57 days** and hospital visits from **52 to 43 days** — both inside the 2026 targets of 62 and 48 days set in the Shop Performance Standard (p. 4).\n\n| Programme | 12 months ago | Latest | Target |\n|---|---|---|---|\n| Performance restoration | 71 d | **57 d** | 62 d |\n| Hospital visit | 52 d | **43 d** | 48 d |\n\nThe step change in **Mar–May** lines up with the second test cell coming online; the two months above 70 days last winter were customer-induced holds and are excluded from the measure.${DISCLAIMER}`,
      chart: CHARTS.tat, context: CONTEXT.mro,
      tools: [
        { toolName: 'query_shop_visits', input: { metric: 'turnaround_days', group_by: 'month', window: '12m', exclude: 'customer_holds' }, output: { rows: 24, source: 'mro_shop_visits' } },
        { toolName: 'render_chart', input: { title: CHARTS.tat.title, type: 'line' }, output: CHARTS.tat },
      ],
      retrieval: { query: 'turnaround target performance restoration hospital visit', collection: 'Policies & SOPs', top: 'Sanad_Aerotech_Shop_Performance_Standard_2026.pdf p.4' },
    };
  }
  if (/induct|capacity|engine type|compare|slot|quarter/.test(q)) {
    return {
      answer: `**59 engines inducted against 66 slots this quarter — 89% utilisation.** Two lines are at capacity (**V2500-A5**, **CFM56-5B**) and **LEAP-1A** has the most headroom with 3 open slots.\n\n- **At capacity:** V2500-A5 (14/14), CFM56-5B (12/12)\n- **Near capacity:** GEnx-1B (11/12), Trent 700 (9/10)\n- **Headroom:** GE90-115B (6/8), LEAP-1A (7/10)\n\nIf the two V2500 inductions forecast for next month hold, the line goes to a 9-day wait; the planning guide recommends offering the LEAP slots to the fleet customers first.${DISCLAIMER}`,
      chart: CHARTS.inductions, context: CONTEXT.mro,
      tools: [
        { toolName: 'query_shop_visits', input: { metric: 'inductions', group_by: 'engine_type', period: 'current_quarter' }, output: { rows: 6, source: 'mro_shop_visits' } },
        { toolName: 'query_capacity', input: { group_by: 'engine_type', period: 'current_quarter' }, output: { rows: 6, source: 'mro_slot_plan' } },
        { toolName: 'render_chart', input: { title: CHARTS.inductions.title, type: 'bar' }, output: CHARTS.inductions },
      ],
      retrieval: { query: 'induction capacity slot planning', collection: 'Engine Maintenance Manuals', top: 'Workscope_Planning_Guide.pdf p.21' },
    };
  }
  if (/lease|portfolio|exposure|region|lessee/.test(q)) {
    return {
      answer: `**The book is Middle East-weighted but inside policy.** The region carries **38%** of net book value, under the 45% concentration limit in the Portfolio Policy (p. 9). Europe (24%) and Asia-Pacific (19%) follow; no single lessee exceeds 11%.\n\n**Watch items**\n1. Three Europe assets reach lease expiry within 18 months and are in remarketing.\n2. Africa exposure doubled year on year from a low base (7%).\n3. Credit-tier mix is unchanged: 71% tier 1–2.${DISCLAIMER}`,
      chart: CHARTS.exposure, context: CONTEXT.lease,
      tools: [
        { toolName: 'query_lease_book', input: { metric: 'net_book_value', group_by: 'region', as_of: 'latest' }, output: { rows: 5, source: 'lease_book' } },
        { toolName: 'render_chart', input: { title: CHARTS.exposure.title, type: 'pie' }, output: CHARTS.exposure },
      ],
      retrieval: { query: 'portfolio concentration limits region lessee', collection: 'Policies & SOPs', top: 'Sanad_Capital_Portfolio_Policy.pdf p.9' },
    };
  }
  return {
    answer: `**Borescope after a hot-section repair: inspect before release, then at 250 cycles.** SOP-QA-017 §7.4 (p. 12) requires a borescope of the HPT stage-1 nozzle guide vanes and blades before the engine leaves the shop, and again at the first **250 cycles** in service.\n\nIf blade coating loss above **15%** of the airfoil area is found, the interval tightens to **100 cycles** until two consecutive clean inspections are on record (Table 3, p. 14). Every inspection goes into the shop-visit file and the fleet health dashboard.\n\n> You asked ${agentName}: _${content}_${DISCLAIMER}`,
    chart: null, context: CONTEXT.sop,
    tools: [
      { toolName: 'retrieve_documents', input: { query: content, collection: 'Policies & SOPs', k: 4 }, output: { documents: 2 } },
    ],
    retrieval: { query: content, collection: 'Policies & SOPs', top: 'SOP-QA-017_Borescope_Inspection_Intervals.pdf p.12' },
  };
}

// ── State ────────────────────────────────────────────────────────────────
const sessions = new Map();   // sessionId → { id, title, insertTimestamp, updateTimestamp, agentId, collectionIds, queries: [] }
const runs = new Map();       // queryId → { startedAt, result, steps: [{at, kind, call}] }

export const getHealth = async () => ({ status: 'ok', mode: 'demo', authenticated: true, ramUrl: '(in-browser showcase)' });
export const getAgents = async () => { await sleep(250); return AGENTS; };
export const getCollections = async () => { await sleep(250); return COLLECTIONS; };
export const getSessions = async () =>
  [...sessions.values()].sort((a, b) => (b.updateTimestamp > a.updateTimestamp ? 1 : -1))
    .map(({ queries, ...s }) => s);
export const getSessionQueries = async (sessionId) => sessions.get(sessionId)?.queries ?? [];
export const deleteSession = async (sessionId) => { sessions.delete(sessionId); return { ok: true }; };

export const extractAttachment = async (file) => {
  const text = await file.text().catch(() => '');
  const MAX = 20000;
  return { name: file.name, text: text.slice(0, MAX), chars: text.length, truncated: text.length > MAX };
};

export const submitQuery = async ({ content, agentId, collectionIds, querySessionId }) => {
  await sleep(300);
  const sid = querySessionId || uuid();
  const ts = now();
  const session = sessions.get(sid) || {
    id: sid, title: content.slice(0, 60), insertTimestamp: ts, updateTimestamp: ts,
    agentId: agentId || null, collectionIds: collectionIds || [], queries: [],
  };
  session.updateTimestamp = ts;
  sessions.set(sid, session);

  const agent = AGENTS.find(a => a.id === agentId);
  const targetName = agent ? agent.name : 'the selected collection';
  const s = script(content, targetName);
  const queryId = uuid();

  const toolCalls = s.tools.map(c => ({ id: uuid(), parentQueryId: queryId, ...c, cost: 0 }));
  const retrievalCalls = [{ id: uuid(), parentQueryId: queryId,
    input: { query: s.retrieval.query, k: 4, collection: s.retrieval.collection },
    output: { documents: s.context.length, top: s.retrieval.top } }];
  const llmCalls = [{ id: uuid(), parentQueryId: queryId, llmId: 'showcase-llm',
    input: { content, modelName: 'claude-sonnet-5-5', modelProvider: 'anthropic', temperature: 0.2 },
    output: { response: s.answer, toolCalls: [] },
    promptTokens: 1840, completionTokens: 312, promptCost: 0.0055, completionCost: 0.0047 }];

  // The trace fills in over ~3.5 s: retrieval first, then each tool, then the model.
  const t0 = Date.now();
  const steps = [];
  let at = 500;
  steps.push({ at, kind: 'retrievalCalls', call: retrievalCalls[0] });
  for (const c of toolCalls) { at += 650; steps.push({ at, kind: 'toolCalls', call: c }); }
  at += 700;
  steps.push({ at, kind: 'llmCalls', call: llmCalls[0] });
  const doneAt = at + 600;

  const result = {
    queryId, querySessionId: sid, content, target: agentId ? 'agent' : 'collection',
    answer: s.answer, context: s.context, toolCalls: toolCalls.map(({ id, parentQueryId, cost, ...c }) => c),
    usage: { llmPromptTokens: 1840, llmCompletionTokens: 312, llmTotalTokens: 2152, llmTotalCost: 0.0102 },
    errorCode: 0, errorText: null, origin: 'user', parentQueryId: null, updateTimestamp: ts,
  };
  runs.set(queryId, { startedAt: t0, steps, doneAt, result });
  session.queries.push(result);

  return { queryId, querySessionId: sid, pollInterval: 1, timeout: 60 };
};

export const getQueryStatus = async (queryId) => {
  const run = runs.get(queryId);
  if (!run) throw new Error('Unknown query');
  const done = Date.now() - run.startedAt >= run.doneAt;
  return done ? { done: true, result: run.result } : { done: false };
};

export const getQueryTrace = async (queryId) => {
  const run = runs.get(queryId);
  if (!run) return { toolCalls: [], llmCalls: [], retrievalCalls: [] };
  const elapsed = Date.now() - run.startedAt;
  const out = { toolCalls: [], llmCalls: [], retrievalCalls: [] };
  for (const s of run.steps) if (s.at <= elapsed) out[s.kind].push(s.call);
  return out;
};
