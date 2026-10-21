import { useLanguage } from '../lib/LanguageContext';
import TargetSelector from './TargetSelector';

/** Conversation title on the left; agent picker, showcase badge and language toggle on the right. */
export default function TopBar({ title, demo, targetProps }) {
  const { t, toggle } = useLanguage();
  return (
    <div className="sn-topbar">
      <div className="sn-title">
        <span className="sn-title-bar" />
        <span className="text">{title}</span>
      </div>
      <div className="sn-topbar-right">
        {demo && <span className="sn-pill sand" title={t('demoHint')}>{t('demoMode')}</span>}
        <TargetSelector {...targetProps} />
        <button className="sn-lang" onClick={toggle} title="English / عربي">{t('langButton')}</button>
      </div>
    </div>
  );
}
