import { useEffect, useRef, useState } from 'react';
import { useApp } from '../context/AppContext';

/* Team sign-in. Shown over the whole app until this browser has signed in as a team,
   when the deployment runs one SAS Viya + SAS RAM pair per team. The team account
   (team3 / its password) only chooses the environments; RAM itself still asks for
   the participant's own RAM sign-in on the SAS RAM tab. */
export default function TeamGate() {
  const { teamsEnabled, teamsLoaded, team, signInTeam } = useApp();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const first = useRef(null);
  const open = teamsLoaded && teamsEnabled && !team;
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
      <form className="team-gate-card glass-card" onSubmit={submit}>
        <div className="section-eyebrow">Emirates Health Services × SAS</div>
        <h2 id="team-gate-title" className="team-gate-title">Sign in as your team</h2>
        <p className="team-gate-lede">
          Each team has its own SAS Viya and SAS RAM. Your team name and password are on the card at your table.
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
      </form>
    </div>
  );
}
