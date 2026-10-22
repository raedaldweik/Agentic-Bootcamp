// UI strings. One place for every label the app shows.

const STR = {
  appTitle: 'Sanad AI',
  tagline: 'Engineering intelligence',
  mubadala: 'A Mubadala company',
  eyebrow: 'Engineering intelligence on SAS Retrieval Agent Manager',
  poweredBy: 'Powered by SAS Retrieval Agent Manager',

  connecting: 'Connecting…',
  connected: 'Connected',
  mockMode: 'Mock mode',
  demoMode: 'Showcase mode',
  demoHint: 'No backend reachable — answers are a built-in design preview with synthetic figures.',
  signInRequired: 'Sign in required',
  notConfigured: 'Not configured',
  backendOffline: 'Backend offline',
  you: 'You',
  system: 'System',

  // Sign-in (Keycloak device flow / Viya paste-the-code flow)
  signIn: 'Sign in',
  signOut: 'Sign out',
  signOutTitle: 'Sign out of RAM on this browser',
  signInTitle: 'Sign in to Sanad AI',
  signInSso: 'Authenticate through single sign-on',
  signInRam: 'Authenticate with your RAM credentials',
  codeInstructions: 'A sign-in page just opened in a new tab. Log in there — it will show you an authorization code. Copy it and paste it below.',
  openSignInPage: 'Open sign-in page ↗',
  pasteCode: 'Paste authorization code…',
  connect: 'Connect',
  deviceInstructions: 'Open the verification page, sign in with your RAM credentials, and enter this code:',
  openVerification: 'Open verification page ↗',
  waitingApproval: 'Waiting for approval…',
  close: 'Close',
  cancel: 'Cancel',

  // Sidebar
  recentConversations: 'Recent conversations',
  newConversation: '+ New conversation',
  newConversationTitle: 'New conversation',
  rename: 'Rename',
  delete: 'Delete',
  noConversations: 'Nothing here yet — your conversations with this agent will appear here.',
  collapse: 'Collapse sidebar',
  expand: 'Expand sidebar',

  // Welcome hero
  heroEyebrow: 'Sanad AI · engineering intelligence',
  heroTitle: 'What can I support you with?',
  heroSub: 'Ask about engine shop visits, turnaround, lease portfolios or any document in your collections. Every answer shows its tool calls, retrieval and sources.',
  heroHint: 'Press / to focus · Enter to send · Shift+Enter for a new line',
  welcome: 'Welcome to Sanad AI. Pick an agent published in RAM from the dropdown above and ask about engine shop visits, turnaround, lease portfolios or your documents. Every answer shows its tool calls, retrieval and sources.',

  // Target selector
  selectAgent: 'Select an agent',
  serviceUnreachable: 'Service unreachable',
  agents: 'Agents',
  collections: 'Collections',
  agent: 'agent',
  collection: 'collection',
  noAgents: 'No agents available on this deployment.',

  // Composer
  selectAgentFirst: 'Select an agent from the dropdown first.',
  askAnything: 'Ask {name} anything…',
  selectThenAsk: 'Select an agent above, then ask anything…',
  attachTooltip: 'Attach a document (PDF, DOCX, TXT, CSV…) — its text is sent with your question',
  speakTooltip: 'Speak instead of typing',
  send: 'Send',
  readingDocument: 'Reading document…',
  sentWithNext: '· sent with your next question',
  firstKChars: 'first {n}k chars',
  kChars: '{n}k chars',
  composerHint: 'Enter to send · Shift+Enter for a new line',

  // Live activity
  working: 'Working…',
  thinking: 'Reading the question',
  stepsSoFar: '{n} step{s} so far',
  stepTool: 'tool call',
  stepRetrieval: 'retrieving documents',
  stepLlm: 'language model',
  agentTimeout: 'The agent did not answer within {n}s — the query may still be running on the server.',
  agentErrorPrefix: 'Agent error:',
  errorPrefix: 'Error:',

  // Response card
  toolCallsHeader: 'Agent tool calls · {n} step{s}',
  sources: 'Sources',
  viewPassage: 'Click to view the retrieved passage',
  copy: 'Copy',
  copied: 'Copied',
  openInVA: 'Open in SAS Visual Analytics ↗',
  clickToZoom: 'Click to enlarge',

  // Flight recorder (query details)
  queryDetails: 'Query details',
  queryDetailsHint: 'Details view — tools, LLM calls, retrieval trace',
  loadingTrace: 'loading trace…',
  inputPrompt: 'Input prompt',
  toolCallsSection: 'Tool calls',
  noToolCalls: 'No tool calls recorded for this query.',
  retrievalSection: 'Retrieval calls (RAG)',
  noRetrieval: 'No retrieval calls recorded for this query.',
  llmSection: 'LLM calls',
  noLlm: 'No LLM calls recorded for this query.',
  contextSection: 'Retrieved context',
  noContext: 'No context passages attached to this answer.',
  inputLabel: 'Input',
  outputLabel: 'Output',
  promptLabel: 'Prompt',
  responseLabel: 'Response',
  open: 'open ↗',
  tokens: 'tokens',
  promptCompletion: '{p} prompt · {c} completion',
  retrievedPassage: 'Retrieved passage',
};

// Suggested prompts on the welcome screen: a short label, the prompt that is
// sent, and an icon key handled by the hero component.
export const SUGGESTIONS = [
  { tag: 'MRO', title: 'Shop-visit turnaround trend', prompt: 'Show the engine shop-visit turnaround trend for the last 12 months.' },
  { tag: 'CAPACITY', title: 'Inductions vs slot capacity', prompt: 'Compare inductions by engine type this quarter against slot capacity.' },
  { tag: 'LEASING', title: 'Portfolio exposure by region', prompt: 'Break down the leasing portfolio exposure by region.' },
  { tag: 'SOP', title: 'Borescope intervals after repair', prompt: 'What does the SOP say about borescope inspection intervals after a hot-section repair?' },
];

export function t(key, vars) {
  let s = STR[key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, v);
  return s;
}

/** Components read strings through this so a future locale layer has one seam to plug into. */
export const useStrings = () => ({ t });
