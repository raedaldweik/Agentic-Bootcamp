// Draws the cards the assistant returns: tiles on top, then blocks (tables, flows,
// checklists, comparisons, the blade inspection view ...). The card carries the detail;
// the text beside it says what it means.
import Icon from './Icon';
import BladeView from './BladeView';
import ChartCard from '../ram/ChartCard';

const TONES = ['good', 'warn', 'bad', 'info'];
const tone = (t) => (TONES.includes(t) ? t : 'info');
// ids such as P-4582 must not break at the hyphen when a tile is narrow
const solid = (v) => (typeof v === 'string' ? v.replace(/(\w)-(?=\w)/g, '$1\u2011') : v);
const STATE_TONE = { done: 'good', current: 'info', pending: 'muted', risk: 'bad', blocked: 'bad', warn: 'warn' };
const STATE_ICON = { done: 'check', current: 'clock', pending: 'clock', risk: 'alert', blocked: 'x', warn: 'alert' };
const STATE_WORD = { done: 'Done', current: 'Now', pending: 'Pending', risk: 'At risk', blocked: 'Blocked', warn: 'Check' };

function Cell({ value }) {
  if (value && typeof value === 'object') {
    return <span className={`hub-pill tone-${tone(value.tone)}`}>{value.text}</span>;
  }
  return <>{value ?? ''}</>;
}

function Table({ b }) {
  const highlight = new Set(b.highlight || []);
  return (
    <div className="overflow-x-auto">
      <table className="hub-table">
        <thead><tr>{b.columns.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
        <tbody>
          {b.rows.map((row, r) => (
            <tr key={r} className={highlight.has(r) ? 'is-highlight' : ''}>
              {row.map((v, i) => <td key={i} className={i === 0 ? 'is-key' : ''}><Cell value={v} /></td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Detail({ b }) {
  const p = b.progress;
  const pct = p ? Math.max(0, Math.min(100, (p.value / (p.max || 1)) * 100)) : 0;
  return (
    <div className="space-y-2.5">
      {b.banner && (
        <div className={`hub-callout tone-${tone(b.banner.tone)}`}><span>{b.banner.text}</span></div>
      )}
      <div className="hub-kv">
        {(b.items || []).map((it, i) => (
          <div key={i} className="hub-kv-row">
            <span className="hub-kv-label">{it.label}</span>
            <span className={`hub-kv-value ${it.tone ? `text-${tone(it.tone)}` : ''}`}>{it.value}</span>
          </div>
        ))}
      </div>
      {p && (
        <div>
          <div className="flex justify-between text-[11px] font-semibold mb-1" style={{ color: 'var(--text-dim)' }}>
            <span>{p.label}</span><span>{p.value} of {p.max} {p.unit}</span>
          </div>
          <div className="hub-bar"><div className={`hub-bar-fill tone-${tone(p.tone)}`} style={{ width: `${pct}%` }} /></div>
        </div>
      )}
    </div>
  );
}

function Flow({ b }) {
  return (
    <div className="hub-flow">
      {b.items.map((it, i) => (
        <div key={i} className="hub-flow-item">
          <div className={`hub-flow-node state-${STATE_TONE[it.state] || 'muted'}`}>
            <span className="hub-flow-icon"><Icon name={it.icon || STATE_ICON[it.state] || 'clock'} size={14} /></span>
            <span className="min-w-0">
              <span className="hub-flow-label">{it.label}</span>
              {it.sub && <span className="hub-flow-sub">{it.sub}</span>}
            </span>
          </div>
          {i < b.items.length - 1 && <span className="hub-flow-arrow" aria-hidden="true">›</span>}
        </div>
      ))}
    </div>
  );
}

function Compare({ b }) {
  return (
    <div className="hub-compare">
      {b.items.map((it, i) => (
        <div key={i} className={`hub-compare-box tone-${tone(it.tone)}`}>
          <div className="hub-tile-label">{it.label}</div>
          <div className="hub-compare-value">{solid(it.value)}</div>
          {it.sub && <div className="hub-tile-sub">{it.sub}</div>}
        </div>
      ))}
      {b.delta && <div className={`hub-delta tone-${tone(b.delta.tone)}`}>{b.delta.text}</div>}
    </div>
  );
}

function Timeline({ b }) {
  return (
    <ol className="hub-timeline">
      {b.items.map((it, i) => (
        <li key={i} className={`state-${STATE_TONE[it.state] || 'muted'}`}>
          <span className="hub-timeline-dot" />
          <div className="hub-timeline-label">{it.label}</div>
          {it.sub && <div className="hub-timeline-sub">{it.sub}</div>}
        </li>
      ))}
    </ol>
  );
}

function Checklist({ b }) {
  const done = b.items.filter((i) => i.state === 'done').length;
  return (
    <div>
      <div className="hub-check-summary">
        <div className="hub-bar flex-1"><div className="hub-bar-fill tone-good" style={{ width: `${(done / (b.items.length || 1)) * 100}%` }} /></div>
        <span>{done} of {b.items.length} complete</span>
      </div>
      <ul className="hub-checklist">
        {b.items.map((it, i) => (
          <li key={i} className={`state-${STATE_TONE[it.state] || 'muted'}`}>
            <span className="hub-check-icon"><Icon name={STATE_ICON[it.state] || 'clock'} size={15} /></span>
            <div className="min-w-0 flex-1">
              <div className="hub-check-label">{it.label}</div>
              {it.detail && <div className="hub-check-detail">{it.detail}</div>}
            </div>
            {it.owner && <span className="hub-check-owner">{it.owner}</span>}
            <span className={`hub-pill tone-${STATE_TONE[it.state] === 'muted' ? 'muted' : tone(STATE_TONE[it.state])}`}>{STATE_WORD[it.state] || it.state}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Options({ b }) {
  return (
    <div className="hub-options">
      {b.items.map((it, i) => (
        <div key={i} className="hub-option">
          <span className="hub-option-icon"><Icon name={it.icon || 'route'} size={16} /></span>
          <div className="min-w-0">
            <div className="hub-option-title">{it.title}</div>
            <div className="hub-option-text">{it.text}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function Steps({ b }) {
  return (
    <ol className="hub-steps">
      {b.items.map((it) => (
        <li key={it.n}>
          <span className="hub-step-n">{it.n}</span>
          <div className="min-w-0">
            <div className="hub-step-title">{it.title}</div>
            <div className="hub-step-text">{it.text}</div>
            {it.confirm && <div className="hub-step-confirm"><Icon name="check" size={12} /> Confirm: {it.confirm}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}

function Block({ b }) {
  let body = null;
  switch (b.type) {
    case 'table': body = <Table b={b} />; break;
    case 'detail': body = <Detail b={b} />; break;
    case 'flow': body = <Flow b={b} />; break;
    case 'compare': body = <Compare b={b} />; break;
    case 'timeline': body = <Timeline b={b} />; break;
    case 'checklist': body = <Checklist b={b} />; break;
    case 'options': body = <Options b={b} />; break;
    case 'steps': body = <Steps b={b} />; break;
    case 'blade': body = <BladeView b={b} />; break;
    case 'keyvalues':
      body = (
        <div className="hub-kv">
          {b.items.map((it, i) => (
            <div key={i} className="hub-kv-row"><span className="hub-kv-label">{it.label}</span><span className="hub-kv-value">{it.value}</span></div>
          ))}
        </div>
      );
      break;
    case 'list':
      body = <ul className={`hub-list tone-${tone(b.tone)}`}>{b.items.map((it, i) => <li key={i}>{it}</li>)}</ul>;
      break;
    case 'callout':
      return (
        <div className={`hub-callout tone-${tone(b.tone)}`}>
          <Icon name={b.tone === 'bad' || b.tone === 'warn' ? 'alert' : b.tone === 'good' ? 'check' : 'shield'} size={15} className="shrink-0 mt-[2px]" />
          <span>{b.title && <b>{b.title}. </b>}{b.text}</span>
        </div>
      );
    default: return null;
  }
  return (
    <section>
      {b.title && b.type !== 'callout' && <h4 className="hub-block-title">{b.title}</h4>}
      {body}
    </section>
  );
}

/** `still`: the card was already on screen (shown while the answer streamed), so it does not animate in again. */
export default function Card({ card, still = false }) {
  if (!card) return null;
  const enter = still ? '' : 'animate-slide-up';
  if (card.kind === 'chart') {
    return <div className={`hub-card hub-chart ${enter}`}><ChartCard spec={card} /></div>;
  }
  return (
    <article className={`hub-card ${enter}`}>
      <header className="hub-card-head">
        <span className="hub-card-bar" />
        <div className="min-w-0">
          <h3 className="hub-card-title">{card.title}</h3>
          {card.subtitle && <p className="hub-card-sub">{card.subtitle}</p>}
        </div>
      </header>
      <div className="hub-card-body">
        {card.tiles?.length > 0 && (
          <div className="hub-tiles">
            {card.tiles.map((t, i) => (
              <div key={i} className={`hub-tile tone-${tone(t.tone)}`}>
                <span className="hub-tile-icon"><Icon name={t.icon || 'target'} size={15} /></span>
                <div className="min-w-0">
                  <div className="hub-tile-label">{t.label}</div>
                  <div className="hub-tile-value">{solid(t.value)}</div>
                  {t.sub && <div className="hub-tile-sub">{t.sub}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
        {(card.blocks || []).map((b, i) => <Block key={i} b={b} />)}
      </div>
    </article>
  );
}
