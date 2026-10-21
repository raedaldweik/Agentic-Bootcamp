import { useStrings } from '../lib/strings';
import TargetSelector from './TargetSelector';

/** Conversation title on the left; showcase badge and agent picker on the right. */
export default function TopBar({ title, demo, targetProps }) {
  const { t } = useStrings();
  return (
    <div className="sn-topbar">
      <div className="sn-title">
        <span className="sn-title-bar" />
        <span className="text">{title}</span>
      </div>
      <div className="sn-topbar-right">
        {demo && <span className="sn-pill sand" title={t('demoHint')}>{t('demoMode')}</span>}
        <TargetSelector {...targetProps} />
      </div>
    </div>
  );
}
