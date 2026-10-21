import { useState, useEffect, useRef } from 'react';
import { startDeviceAuth, pollDeviceAuth, submitViyaCode, saveSession } from '../lib/api';
import { useLanguage } from '../lib/LanguageContext';
import { SanadMark } from './Logo';

/**
 * "Sign in" button + modal for a RAM deployment that needs an interactive
 * login (health.status === 'signin_required'). Two flows, chosen by the
 * backend (health.signinFlow): "device" (Keycloak device code) or "code"
 * (Viya SASLogon, paste the authorization code). On success the page reloads.
 */
export default function SignIn({ health }) {
  const { t } = useLanguage();
  const [signin, setSignin] = useState(null);
  const [signinError, setSigninError] = useState(null);
  const [viyaCode, setViyaCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const pollTimer = useRef(null);

  useEffect(() => () => clearTimeout(pollTimer.current), []);
  const isViyaFlow = health?.signinFlow === 'code';

  const beginDeviceSignin = async () => {
    setSigninError(null);
    try {
      const info = await startDeviceAuth();
      setSignin({ kind: 'device', ...info });
      let interval = Math.max(info.interval || 5, 3) * 1000;
      const tick = async () => {
        try {
          const res = await pollDeviceAuth();
          if (res.ok) { saveSession(res.session); window.location.reload(); return; }
          if (res.slowDown) interval += 2000;
        } catch (e) { setSigninError(e.message); return; }
        pollTimer.current = setTimeout(tick, interval);
      };
      pollTimer.current = setTimeout(tick, interval);
    } catch (e) {
      setSigninError(e.message);
      setSignin({ kind: 'device' });
    }
  };

  const beginSignin = () => {
    if (isViyaFlow) {
      setSigninError(null); setViyaCode('');
      setSignin({ kind: 'code', authorizeUrl: health.authorizeUrl });
      if (health.authorizeUrl) window.open(health.authorizeUrl, '_blank', 'noopener');
    } else {
      beginDeviceSignin();
    }
  };

  const submitCode = async () => {
    if (!viyaCode.trim() || submitting) return;
    setSubmitting(true); setSigninError(null);
    try {
      const res = await submitViyaCode(viyaCode);
      if (res.ok) { saveSession(res.session); window.location.reload(); return; }
    } catch (e) { setSigninError(e.message); }
    setSubmitting(false);
  };

  const cancel = () => { clearTimeout(pollTimer.current); setSignin(null); setSigninError(null); };

  return (
    <>
      <button onClick={beginSignin} className="sn-btn sn-btn-primary">{t('signIn')}</button>
      {signin && (
        <div className="sn-backdrop" style={{ zIndex: 100 }}>
          <div className="sn-modal" style={{ maxWidth: 460 }} role="dialog" aria-modal="true">
            <div className="sn-modal-head">
              <div className="sn-modal-title">
                <div className="sn-mark-tile" style={{ width: 36, height: 36 }}><SanadMark size={20} /></div>
                <span>{t('signInTitle')}<span className="sub">{signin.kind === 'code' ? t('signInSso') : t('signInRam')}</span></span>
              </div>
            </div>
            <div className="sn-modal-body">
              {signinError && <div className="sn-alert">{signinError}</div>}
              {signin.kind === 'code' ? (
                <>
                  <p className="text-[12.5px] leading-relaxed" style={{ color: 'var(--text-md)' }}>{t('codeInstructions')}</p>
                  <a href={signin.authorizeUrl} target="_blank" rel="noreferrer" className="sn-btn sn-btn-primary w-full">{t('openSignInPage')}</a>
                  <div className="flex gap-2">
                    <input className="sn-input font-mono" value={viyaCode} onChange={e => setViyaCode(e.target.value)} onKeyDown={e => e.key === 'Enter' && submitCode()}
                      placeholder={t('pasteCode')} autoFocus dir="ltr" />
                    <button onClick={submitCode} disabled={submitting} className="sn-btn sn-btn-primary">{submitting ? '…' : t('connect')}</button>
                  </div>
                </>
              ) : !signinError && (
                <>
                  <p className="text-[12.5px] leading-relaxed" style={{ color: 'var(--text-md)' }}>{t('deviceInstructions')}</p>
                  <div className="sn-code-box" dir="ltr">{signin.userCode}</div>
                  <a href={signin.verificationUriComplete || signin.verificationUri} target="_blank" rel="noreferrer" className="sn-btn sn-btn-primary w-full">{t('openVerification')}</a>
                  <div className="flex items-center justify-center gap-2 text-[11px]" style={{ color: 'var(--text-dim)' }}>
                    <span className="sn-dot ok pulse" />{t('waitingApproval')}
                  </div>
                </>
              )}
              <button onClick={cancel} className="sn-btn sn-btn-ghost w-full">{signinError ? t('close') : t('cancel')}</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
