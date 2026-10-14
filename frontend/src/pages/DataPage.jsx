import { useEffect, useState } from 'react';
import { getCrcDataRows, getCrcDataTables, getDataRows, getDataTables } from '../services/api';
import { Spinner } from '../components/ui';

/** Table browser. Example 1: the HIE, 8 relational tables. Example 2 (source="screening"): the
 *  programme's five tables, the same browser. */
const SOURCES = {
  hie: { tables: getDataTables, rows: getDataRows, first: 'patient_summary', title: 'HIE tables',
         sub: 'A real exchange shape: coded, longitudinal, relational.' },
  screening: { tables: getCrcDataTables, rows: getCrcDataRows, first: 'population', title: 'Programme tables',
               sub: 'The population, every invitation, every FIT and colonoscopy: what the rules, the model and the agent read.' },
};

export default function DataPage({ source = 'hie' }) {
  const src = SOURCES[source] || SOURCES.hie;
  const [tables, setTables] = useState(null);
  const [active, setActive] = useState(src.first);
  const [rows, setRows] = useState(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const limit = 40;

  const [loadedFrom, setLoadedFrom] = useState(null);
  useEffect(() => { src.tables().then((r) => { setTables(r.tables); setLoadedFrom(r.source || null); }).catch(() => setTables([])); }, [source]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    setRows(null);
    src.rows(active, offset, limit, search)
      .then((r) => { setRows(r.rows); setTotal(r.total); })
      .catch(() => setRows([]));
  }, [active, offset, search, source]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!tables) return <Spinner />;
  const activeMeta = tables.find((t) => t.name === active);
  const cols = rows?.length ? Object.keys(rows[0]) : (activeMeta?.columns || []);

  return (
    <div className="h-full flex gap-4 p-4">
      <div className="w-[250px] shrink-0 glass-card flex flex-col min-h-0">
        <div className="p-4 border-b border-[rgba(15,23,42,0.07)]">
          <p className="panel-title">{src.title}</p>
          <p className="text-[10px] mt-1.5 leading-snug" style={{ color: 'var(--text-dim)' }}>
            {src.sub}
          </p>
          {loadedFrom && src === SOURCES.hie && (
            <p className="text-[9.5px] mt-1.5 font-bold" style={{ color: loadedFrom.loaded_from === 'bigquery' ? 'var(--green)' : 'var(--text-dim)' }}>
              {loadedFrom.loaded_from === 'bigquery'
                ? `● BigQuery · ${loadedFrom.project}.${loadedFrom.dataset} · ${loadedFrom.location}${loadedFrom.load_ms ? ` · loaded in ${(loadedFrom.load_ms / 1000).toFixed(1)} s` : ''}`
                : loadedFrom.provisioning ? `◐ provisioning BigQuery ${loadedFrom.dataset}…`
                : loadedFrom.backend === 'bigquery' ? `○ local files (BigQuery: ${loadedFrom.error || 'pending'})`
                : '○ local csv.gz files · on Viya: CAS in-memory tables loaded from the exchange export'}
            </p>
          )}
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {tables.map((t) => (
            <button key={t.name} onClick={() => { setActive(t.name); setOffset(0); setSearch(''); }}
              className="w-full text-left px-3 py-2 rounded-lg transition-all"
              style={t.name === active
                ? { background: 'rgba(43,83,120,0.12)', border: '1px solid rgba(43,83,120,0.30)', borderLeft: '3px solid var(--brand)' }
                : { border: '1px solid transparent' }}>
              <p className="text-[12px] font-bold" style={{ color: t.name === active ? 'var(--brand-lo)' : 'var(--text-md)' }}>
                {t.name}
              </p>
              <p className="text-[9.5px]" style={{ color: 'var(--text-faint)' }}>
                {t.rows.toLocaleString()} rows · {t.columns.length} cols
              </p>
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 glass-card flex flex-col min-w-0 min-h-0">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[rgba(15,23,42,0.07)]">
          <div className="min-w-0 flex-1">
            <p className="text-[13px] font-bold" style={{ color: 'var(--text)' }}>{active}</p>
            <p className="text-[10px] truncate" style={{ color: 'var(--text-dim)' }}>{activeMeta?.description}</p>
          </div>
          <input value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }}
            placeholder="Search rows…"
            className="w-[180px] px-3 py-1.5 rounded-lg text-[11.5px] outline-none border"
            style={{ background: 'rgba(255,255,255,0.6)', borderColor: 'rgba(15,23,42,0.12)', color: 'var(--text)' }} />
          <div className="flex items-center gap-1.5 text-[10.5px]" style={{ color: 'var(--text-dim)' }}>
            <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}
              className="px-2 py-1 rounded disabled:opacity-30 hover:bg-[rgba(43,83,120,0.08)]">◀</button>
            {offset + 1}–{Math.min(offset + limit, total)} of {total.toLocaleString()}
            <button disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}
              className="px-2 py-1 rounded disabled:opacity-30 hover:bg-[rgba(43,83,120,0.08)]">▶</button>
          </div>
        </div>
        <div className="flex-1 overflow-auto">
          {rows === null ? <Spinner /> : (
            <table className="data-table">
              <thead>
                <tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    {cols.map((c) => (
                      <td key={c} className="max-w-[220px] overflow-hidden text-ellipsis">
                        {r[c] === null || r[c] === undefined ? 'n/a' : String(r[c])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
