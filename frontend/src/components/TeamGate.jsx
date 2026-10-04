import { useEffect, useRef, useState } from 'react';
import { useApp } from '../context/AppContext';

/* Team sign-in. Shown over the whole app until this browser has signed in as a team,
   when the deployment has team environments. It cannot be dismissed: the team account
   (team3 / its password) is what chooses the environments. */
export default function TeamGate() {
  const { gateOpen: open, signInTeam } = useApp();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const first = useRef(null);
  useEffect(() => { if (open) setTimeout(() => first.current?.focus(), 50); }, [open]);
  if (!open) return null;

  const submit = async (e) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true); setError('');
    try { await signInTeam(username.trim(), password); }
    catch (err) { setError(err.message === 'Wrong team name or password.' ? err.message : 'Could not sign in. Try again.'); }
    setBusy(false);
  };

  return (
    <div className="team-gate" role="dialog" aria-modal="true" aria-labelledby="team-gate-title">
      <form className="team-gate-card" onSubmit={submit}>
        <div className="section-eyebrow">Emirates Health Services × SAS</div>
        <h2 id="team-gate-title" className="team-gate-title">Sign in as your team</h2>
        <p className="team-gate-lede">
          Your team name and password are on the card at your table, for example team3 / team3.
        </p>
        <label className="team-gate-label" htmlFor="team-user">Team</label>
        <input id="team-user" ref={first} className="team-gate-input" value={username} autoComplete="username"
          onChange={(e) => setUsername(e.target.value)} placeholder="team3" autoCapitalize="none" spellCheck={false} />
        <label className="team-gate-label" htmlFor="team-pass">Password</label>
        <input id="team-pass" type="password" className="team-gate-input" value={password} autoComplete="current-password"
          onChange={(e) => setPassword(e.target.value)} placeholder="••••••" />
        {error && <div className="team-gate-error">{error}</div>}
        <button type="submit" className="btn-primary team-gate-btn" disabled={busy || !username || !password}>
          {busy ? 'Signing in…' : 'Enter the hackathon'}
        </button>
        <div className="team-gate-note">You sign in once on this computer. Your team's Viya and RAM, with their sign-in details, are on the home page after that.</div>
      </form>
    </div>
  );
}
