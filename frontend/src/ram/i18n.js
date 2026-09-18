// UI strings for the SAS RAM page — English / Arabic. The toggle in the
// page's top bar switches the page (and flips the page container to RTL; the
// host app's document direction is never touched). The backend is told the
// language per query for compatibility; RAM agents answer as configured.

const STR = {
  appTitle: { en: 'SAS RAM · Retrieval Agent Manager', ar: 'SAS RAM · مدير وكلاء الاسترجاع' },
  connecting: { en: 'Connecting…', ar: 'جارٍ الاتصال…' },
  connected: { en: 'Connected', ar: 'متصل' },
  mockMode: { en: 'Mock mode', ar: 'وضع المحاكاة' },
  signInRequired: { en: 'Sign in required', ar: 'يلزم تسجيل الدخول' },
  notConfigured: { en: 'Not configured', ar: 'غير مُهيّأ' },
  backendOffline: { en: 'Backend offline', ar: 'الخادم غير متصل' },
  langButton: { en: 'عربي', ar: 'English' },
  you: { en: 'You', ar: 'أنت' },

  // Sign-in (Keycloak device flow / Viya paste-the-code flow)
  signIn: { en: 'Sign in', ar: 'تسجيل الدخول' },
  signOut: { en: 'Sign out', ar: 'تسجيل الخروج' },
  signOutTitle: { en: 'Sign out of SAS RAM on this browser', ar: 'تسجيل الخروج من SAS RAM على هذا المتصفح' },
  signInTitle: { en: 'Sign in to your assistant', ar: 'سجّل الدخول إلى مساعدك' },
  signInSso: { en: 'Authenticate through single sign-on', ar: 'المصادقة عبر تسجيل الدخول الموحّد' },
  signInRam: { en: 'Authenticate with your RAM credentials', ar: 'المصادقة ببيانات اعتماد RAM الخاصة بك' },
  codeInstructions: {
    en: 'A sign-in page just opened in a new tab. Log in there — it will show you an authorization code. Copy it and paste it below.',
    ar: 'فُتحت صفحة تسجيل الدخول في تبويب جديد. سجّل الدخول هناك — ستظهر لك رمز تفويض. انسخه والصقه أدناه.',
  },
  openSignInPage: { en: 'Open sign-in page ↗', ar: 'فتح صفحة تسجيل الدخول ↗' },
  pasteCode: { en: 'Paste authorization code…', ar: 'الصق رمز التفويض…' },
  connect: { en: 'Connect', ar: 'اتصال' },
  deviceInstructions: {
    en: 'Open the verification page, sign in with your RAM credentials, and enter this code:',
    ar: 'افتح صفحة التحقق، وسجّل الدخول ببيانات اعتماد RAM، ثم أدخل هذا الرمز:',
  },
  openVerification: { en: 'Open verification page ↗', ar: 'فتح صفحة التحقق ↗' },
  waitingApproval: { en: 'Waiting for approval…', ar: 'في انتظار الموافقة…' },
  close: { en: 'Close', ar: 'إغلاق' },
  cancel: { en: 'Cancel', ar: 'إلغاء' },

  recentConversations: { en: 'Recent conversations', ar: 'المحادثات الأخيرة' },
  newConversation: { en: '+ New conversation', ar: '+ محادثة جديدة' },
  newConversationTitle: { en: 'New conversation', ar: 'محادثة جديدة' },
  rename: { en: 'Rename', ar: 'إعادة تسمية' },
  delete: { en: 'Delete', ar: 'حذف' },

  welcome: {
    en: 'Welcome to the EHS Agentic AI Bootcamp assistant on SAS Retrieval Agent Manager (RAM). Pick an agent published in RAM from the dropdown above and ask about the diabetes population, care gaps, guidelines or a policy simulation. Every answer shows its tool calls, retrieval and sources.',
    ar: 'مرحباً بك في مساعد معسكر EHS للذكاء الاصطناعي الوكيل على SAS Retrieval Agent Manager. اختر وكيلاً منشوراً في RAM من القائمة أعلاه واسأل عن مرضى السكري، أو فجوات الرعاية، أو الإرشادات السريرية، أو محاكاة سياسة. كل إجابة تعرض استدعاءات أدواتها وعمليات الاسترجاع ومصادرها.',
  },

  selectAgent: { en: 'Select an agent', ar: 'اختر وكيلاً' },
  serviceUnreachable: { en: 'Service unreachable', ar: 'تعذّر الوصول إلى الخدمة' },
  agents: { en: 'Agents', ar: 'الوكلاء' },
  collections: { en: 'Collections', ar: 'المجموعات' },
  noAgents: { en: 'No agents available on this deployment.', ar: 'لا يوجد وكلاء متاحون في هذا النشر.' },

  selectAgentFirst: { en: 'Select an agent from the dropdown first.', ar: 'اختر وكيلاً من القائمة أولاً.' },
  askAnything: { en: 'Ask {name} anything…', ar: 'اسأل {name} أي شيء…' },
  selectThenAsk: { en: 'Select an agent above, then ask anything…', ar: 'اختر وكيلاً من الأعلى ثم اسأل أي شيء…' },
  attachTooltip: {
    en: 'Attach a document (PDF, DOCX, TXT, CSV…) — its text is sent with your question',
    ar: 'أرفق مستنداً (PDF، DOCX، TXT، CSV…) — يُرسل نصه مع سؤالك',
  },
  speakTooltip: { en: 'Speak instead of typing', ar: 'تحدّث بدلاً من الكتابة' },
  readingDocument: { en: 'Reading document…', ar: 'جارٍ قراءة المستند…' },
  sentWithNext: { en: '· sent with your next question', ar: '· يُرسل مع سؤالك التالي' },
  firstKChars: { en: 'first {n}k chars', ar: 'أول {n} ألف حرف' },
  kChars: { en: '{n}k chars', ar: '{n} ألف حرف' },
  stepsSoFar: { en: '{n} step{s} so far', ar: '{n} خطوة حتى الآن' },
  agentTimeout: {
    en: 'The agent did not answer within {n}s — the query may still be running on the server.',
    ar: 'لم يُجب الوكيل خلال {n} ثانية — قد يكون الاستعلام لا يزال قيد التنفيذ على الخادم.',
  },
  agentErrorPrefix: { en: 'Agent error:', ar: 'خطأ من الوكيل:' },
  errorPrefix: { en: 'Error:', ar: 'خطأ:' },

  toolCallsHeader: { en: 'Agent tool calls · {n} step{s}', ar: 'استدعاءات أدوات الوكيل · {n} خطوة' },

  openInVA: { en: 'Open in SAS Visual Analytics ↗', ar: 'فتح في SAS Visual Analytics ↗' },
  clickToZoom: { en: 'Click to enlarge', ar: 'انقر للتكبير' },

  queryDetails: { en: 'Query details', ar: 'تفاصيل الاستعلام' },
  loadingTrace: { en: 'loading trace…', ar: 'جارٍ تحميل الأثر…' },
  inputPrompt: { en: 'Input prompt', ar: 'نص السؤال' },
  toolCallsSection: { en: 'Tool calls', ar: 'استدعاءات الأدوات' },
  noToolCalls: { en: 'No tool calls recorded for this query.', ar: 'لا توجد استدعاءات أدوات مسجّلة لهذا الاستعلام.' },
  retrievalSection: { en: 'Retrieval calls (RAG)', ar: 'استدعاءات الاسترجاع (RAG)' },
  noRetrieval: { en: 'No retrieval calls recorded for this query.', ar: 'لا توجد استدعاءات استرجاع مسجّلة لهذا الاستعلام.' },
  llmSection: { en: 'LLM calls', ar: 'استدعاءات النموذج اللغوي' },
  noLlm: { en: 'No LLM calls recorded for this query.', ar: 'لا توجد استدعاءات نموذج لغوي مسجّلة لهذا الاستعلام.' },
  contextSection: { en: 'Retrieved context', ar: 'السياق المسترجَع' },
  noContext: { en: 'No context passages attached to this answer.', ar: 'لا توجد مقاطع سياق مرفقة بهذه الإجابة.' },
  inputLabel: { en: 'Input', ar: 'المدخلات' },
  outputLabel: { en: 'Output', ar: 'المخرجات' },
  promptLabel: { en: 'Prompt', ar: 'الموجّه' },
  responseLabel: { en: 'Response', ar: 'الاستجابة' },
  open: { en: 'open ↗', ar: 'فتح ↗' },
  tokens: { en: 'tokens', ar: 'رمز' },
  promptCompletion: { en: '{p} prompt · {c} completion', ar: '{p} إدخال · {c} إخراج' },
};


export function translate(lang, key, vars) {
  const entry = STR[key];
  let s = (entry && (entry[lang] ?? entry.en)) ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, v);
  }
  return s;
}
