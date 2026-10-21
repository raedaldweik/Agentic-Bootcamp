import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { translate } from './i18n';

const LanguageContext = createContext();

// App-wide language state. The shell applies dir={isRTL ? 'rtl' : 'ltr'} on
// its own container, so every component simply uses logical CSS (ps/pe/ms/me).
export function LanguageProvider({ children }) {
  const [lang, setLang] = useState(() => {
    try { return localStorage.getItem('sanad-ui-lang') || 'en'; } catch { return 'en'; }
  });

  useEffect(() => {
    try { localStorage.setItem('sanad-ui-lang', lang); } catch { /* private mode */ }
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
