import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { translate } from './i18n';

const LanguageContext = createContext();

// Page-scoped language state. Deliberately does NOT touch
// document.documentElement.dir/lang — that would flip the whole host app.
// The page root applies dir={isRTL ? 'rtl' : 'ltr'} on its own container.
export function LanguageProvider({ children }) {
  const [lang, setLang] = useState(() => {
    try { return localStorage.getItem('ram-ui-lang') || 'en'; } catch { return 'en'; }
  });

  useEffect(() => {
    try { localStorage.setItem('ram-ui-lang', lang); } catch { /* private mode */ }
  }, [lang]);

  const t = useCallback((key, vars) => translate(lang, key, vars), [lang]);
  const toggle = useCallback(() => setLang(l => (l === 'ar' ? 'en' : 'ar')), []);

  return (
    <LanguageContext.Provider value={{ lang, setLang, t, toggle, isRTL: lang === 'ar' }}>
      {children}
    </LanguageContext.Provider>
  );
}

export const useLanguage = () => useContext(LanguageContext);
