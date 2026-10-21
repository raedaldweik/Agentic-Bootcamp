// UI strings — English / Arabic. The toggle in the top bar switches the whole
// app and flips the shell to RTL. The backend is told the language per query
// for compatibility; RAM agents answer as configured.

const STR = {
  appTitle: { en: 'Sanad AI', ar: 'سند الذكي' },
  tagline: { en: 'Engineering intelligence', ar: 'ذكاء هندسي' },
  mubadala: { en: 'A Mubadala company', ar: 'إحدى شركات مبادلة' },
  poweredBy: { en: 'Powered by SAS Retrieval Agent Manager', ar: 'مدعوم بـ SAS Retrieval Agent Manager' },

  connecting: { en: 'Connecting…', ar: 'جارٍ الاتصال…' },
  connected: { en: 'Connected', ar: 'متصل' },
  mockMode: { en: 'Mock mode', ar: 'وضع المحاكاة' },
  demoMode: { en: 'Showcase mode', ar: 'وضع العرض' },
  demoHint: { en: 'No backend reachable — answers are a built-in design preview with synthetic figures.', ar: 'لا يوجد خادم متاح — الإجابات معاينة تصميم مدمجة بأرقام افتراضية.' },
  signInRequired: { en: 'Sign in required', ar: 'يلزم تسجيل الدخول' },
  notConfigured: { en: 'Not configured', ar: 'غير مُهيّأ' },
  backendOffline: { en: 'Backend offline', ar: 'الخادم غير متصل' },
  langButton: { en: 'عربي', ar: 'English' },
  you: { en: 'You', ar: 'أنت' },
  system: { en: 'System', ar: 'النظام' },

  // Sign-in (Keycloak device flow / Viya paste-the-code flow)
  signIn: { en: 'Sign in', ar: 'تسجيل الدخول' },
  signOut: { en: 'Sign out', ar: 'تسجيل الخروج' },
  signOutTitle: { en: 'Sign out of RAM on this browser', ar: 'تسجيل الخروج من RAM على هذا المتصفح' },
  signInTitle: { en: 'Sign in to Sanad AI', ar: 'سجّل الدخول إلى سند الذكي' },
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

  // Sidebar
  conversations: { en: 'Conversations', ar: 'المحادثات' },
  newConversation: { en: 'New conversation', ar: 'محادثة جديدة' },
  newConversationTitle: { en: 'New conversation', ar: 'محادثة جديدة' },
  rename: { en: 'Rename', ar: 'إعادة تسمية' },
  delete: { en: 'Delete', ar: 'حذف' },
  noConversations: { en: 'Nothing here yet — your conversations with this agent will appear here.', ar: 'لا شيء هنا بعد — ستظهر محادثاتك مع هذا الوكيل هنا.' },
  collapse: { en: 'Collapse sidebar', ar: 'طي الشريط الجانبي' },
  expand: { en: 'Expand sidebar', ar: 'توسيع الشريط الجانبي' },

  // Welcome hero
  heroEyebrow: { en: 'Sanad AI · engineering intelligence', ar: 'سند الذكي · ذكاء هندسي' },
  heroTitle: { en: 'What can I support you with?', ar: 'كيف يمكنني دعمك اليوم؟' },
  heroSub: {
    en: 'Ask about engine shop visits, turnaround, lease portfolios or any document in your collections. Every answer shows its tool calls, retrieval and sources.',
    ar: 'اسأل عن زيارات ورش المحركات، أو زمن الإنجاز، أو محافظ التأجير، أو أي مستند في مجموعاتك. كل إجابة تعرض استدعاءات أدواتها وعمليات الاسترجاع ومصادرها.',
  },
  heroHint: { en: 'Press / to focus · Enter to send · Shift+Enter for a new line', ar: 'اضغط / للتركيز · Enter للإرسال · Shift+Enter لسطر جديد' },
  welcome: {
    en: 'Welcome to Sanad AI. Pick an agent published in RAM and ask about engine shop visits, turnaround, lease portfolios or your documents.',
    ar: 'مرحباً بك في سند الذكي. اختر وكيلاً منشوراً في RAM واسأل عن زيارات ورش المحركات أو زمن الإنجاز أو محافظ التأجير أو مستنداتك.',
  },

  // Target selector
  selectAgent: { en: 'Select an agent', ar: 'اختر وكيلاً' },
  serviceUnreachable: { en: 'Service unreachable', ar: 'تعذّر الوصول إلى الخدمة' },
  agents: { en: 'Agents', ar: 'الوكلاء' },
  collections: { en: 'Collections', ar: 'المجموعات' },
  agent: { en: 'agent', ar: 'وكيل' },
  collection: { en: 'collection', ar: 'مجموعة' },
  noAgents: { en: 'No agents available on this deployment.', ar: 'لا يوجد وكلاء متاحون في هذا النشر.' },

  // Composer
  selectAgentFirst: { en: 'Select an agent from the dropdown first.', ar: 'اختر وكيلاً من القائمة أولاً.' },
  askAnything: { en: 'Ask {name} anything…', ar: 'اسأل {name} أي شيء…' },
  selectThenAsk: { en: 'Select an agent above, then ask anything…', ar: 'اختر وكيلاً من الأعلى ثم اسأل أي شيء…' },
  attachTooltip: {
    en: 'Attach a document (PDF, DOCX, TXT, CSV…) — its text is sent with your question',
    ar: 'أرفق مستنداً (PDF، DOCX، TXT، CSV…) — يُرسل نصه مع سؤالك',
  },
  speakTooltip: { en: 'Speak instead of typing', ar: 'تحدّث بدلاً من الكتابة' },
  send: { en: 'Send', ar: 'إرسال' },
  readingDocument: { en: 'Reading document…', ar: 'جارٍ قراءة المستند…' },
  sentWithNext: { en: '· sent with your next question', ar: '· يُرسل مع سؤالك التالي' },
  firstKChars: { en: 'first {n}k chars', ar: 'أول {n} ألف حرف' },
  kChars: { en: '{n}k chars', ar: '{n} ألف حرف' },
  composerHint: { en: 'Enter to send · Shift+Enter for a new line', ar: 'Enter للإرسال · Shift+Enter لسطر جديد' },

  // Live activity
  working: { en: 'Working…', ar: 'جارٍ العمل…' },
  thinking: { en: 'Reading the question', ar: 'قراءة السؤال' },
  stepsSoFar: { en: '{n} step{s} so far', ar: '{n} خطوة حتى الآن' },
  stepTool: { en: 'tool call', ar: 'استدعاء أداة' },
  stepRetrieval: { en: 'retrieving documents', ar: 'استرجاع المستندات' },
  stepLlm: { en: 'language model', ar: 'النموذج اللغوي' },
  agentTimeout: {
    en: 'The agent did not answer within {n}s — the query may still be running on the server.',
    ar: 'لم يُجب الوكيل خلال {n} ثانية — قد يكون الاستعلام لا يزال قيد التنفيذ على الخادم.',
  },
  agentErrorPrefix: { en: 'Agent error:', ar: 'خطأ من الوكيل:' },
  errorPrefix: { en: 'Error:', ar: 'خطأ:' },

  // Response card
  toolCallsHeader: { en: 'Agent tool calls · {n} step{s}', ar: 'استدعاءات أدوات الوكيل · {n} خطوة' },
  sources: { en: 'Sources', ar: 'المصادر' },
  viewPassage: { en: 'Click to view the retrieved passage', ar: 'انقر لعرض المقطع المسترجَع' },
  copy: { en: 'Copy', ar: 'نسخ' },
  copied: { en: 'Copied', ar: 'تم النسخ' },
  openInVA: { en: 'Open in SAS Visual Analytics ↗', ar: 'فتح في SAS Visual Analytics ↗' },
  clickToZoom: { en: 'Click to enlarge', ar: 'انقر للتكبير' },

  // Flight recorder (query details)
  flightRecorder: { en: 'Flight recorder', ar: 'مسجّل الرحلة' },
  flightRecorderHint: { en: 'Every tool, retrieval and model call behind this answer', ar: 'كل استدعاء أداة أو استرجاع أو نموذج خلف هذه الإجابة' },
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
  retrievedPassage: { en: 'Retrieved passage', ar: 'المقطع المسترجَع' },
};

// Suggested prompts on the welcome screen. Each carries a short label, the
// prompt that is sent, and an icon key handled by the hero component.
const SUGGESTIONS = {
  en: [
    { icon: 'trend', title: 'Shop-visit turnaround', prompt: 'Show the engine shop-visit turnaround trend for the last 12 months.' },
    { icon: 'bars', title: 'Induction capacity', prompt: 'Compare inductions by engine type this quarter against slot capacity.' },
    { icon: 'pie', title: 'Lease exposure', prompt: 'Break down the leasing portfolio exposure by region.' },
    { icon: 'doc', title: 'Manuals & SOPs', prompt: 'What does the SOP say about borescope inspection intervals after a hot-section repair?' },
  ],
  ar: [
    { icon: 'trend', title: 'زمن إنجاز زيارات الورشة', prompt: 'اعرض اتجاه زمن إنجاز زيارات ورشة المحركات خلال الاثني عشر شهراً الماضية.' },
    { icon: 'bars', title: 'طاقة الإدخال', prompt: 'قارن عمليات إدخال المحركات حسب النوع هذا الربع مع السعة المتاحة.' },
    { icon: 'pie', title: 'تعرّض محفظة التأجير', prompt: 'قسّم تعرّض محفظة التأجير حسب المنطقة.' },
    { icon: 'doc', title: 'الأدلة والإجراءات', prompt: 'ماذا تنص إجراءات التشغيل حول فترات فحص المنظار الداخلي بعد إصلاح القسم الساخن؟' },
  ],
};

export function suggestions(lang) {
  return SUGGESTIONS[lang] || SUGGESTIONS.en;
}

export function translate(lang, key, vars) {
  const entry = STR[key];
  let s = (entry && (entry[lang] ?? entry.en)) ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, v);
  }
  return s;
}
