import { useState } from 'react';
import { useLanguage } from '../lib/LanguageContext';

/** Live snapshot of a SAS Visual Analytics report; click to zoom, link opens the real report. */
export default function ReportCard({ spec }) {
  const { t } = useLanguage();
  const [zoom, setZoom] = useState(false);
  const [failed, setFailed] = useState(false);
  if (!spec?.imageUrl || failed) return null;

  return (
    <div className="sn-report a-slide-up">
      <div className="sn-report-head">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--cyan)" strokeWidth="2" className="shrink-0"><rect x="3" y="3" width="18" height="18" rx="2" /><line x1="3" y1="9" x2="21" y2="9" /><line x1="9" y1="21" x2="9" y2="9" /></svg>
        <span className="truncate">{spec.reportName || 'Visual Analytics report'}</span>
        {spec.sectionName && <span className="sn-pill">{spec.sectionName}</span>}
        <span className="sn-pill cyan ms-auto">SAS VA</span>
      </div>
      <button onClick={() => setZoom(true)} className="block w-full cursor-zoom-in" title={t('clickToZoom')}>
        <img src={spec.imageUrl} alt={spec.reportName || 'report'} onError={() => setFailed(true)} />
      </button>
      {spec.viewerUrl && (
        <div className="sn-report-foot"><a href={spec.viewerUrl} target="_blank" rel="noreferrer">{t('openInVA')}</a></div>
      )}
      {zoom && (
        <div className="sn-backdrop cursor-zoom-out" style={{ zIndex: 400 }} onClick={() => setZoom(false)}>
          <img src={spec.imageUrl} alt="" className="max-w-full max-h-full rounded-xl" style={{ background: '#fff', boxShadow: 'var(--shadow-lg)' }} />
        </div>
      )}
    </div>
  );
}
