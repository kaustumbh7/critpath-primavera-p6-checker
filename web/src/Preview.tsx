import { useEffect, useState } from 'react'
import { fetchTablePage, listTables, type TablePage, type TablesResponse } from './api'

const PAGE = 50
const fmt = (n: number) => n.toLocaleString('en-US')

/** What the parser read from a bundled .xer: every table, and its rows a page at a time. */
export default function Preview({ file, onClose }: { file: string; onClose: () => void }) {
  const [tables, setTables] = useState<TablesResponse | null>(null)
  const [table, setTable] = useState<string | null>(null)
  const [page, setPage] = useState<TablePage | null>(null)
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    listTables(file)
      .then((t) => {
        setTables(t)
        // Open on the activities table when there is one; it is what people want to see.
        const first = t.tables.find((x) => x.name === 'TASK') ?? t.tables[0]
        if (first) setTable(first.name)
      })
      .catch((e: Error) => setError(e.message))
  }, [file])

  useEffect(() => {
    if (!table) return
    let cancelled = false
    setLoading(true)
    fetchTablePage(file, table, offset, PAGE)
      .then((p) => { if (!cancelled) { setPage(p); setError(null) } })
      .catch((e: Error) => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [file, table, offset])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const pick = (name: string) => { setTable(name); setOffset(0); setPage(null) }
  const total = page?.total ?? 0
  const from = total ? offset + 1 : 0
  const to = Math.min(offset + PAGE, total)

  return (
    <div className="modal-back" onClick={onClose} role="presentation">
      <div className="modal" role="dialog" aria-modal="true" aria-label={`Parsed data in ${file}`} onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <div>
            <h2 className="mono">{file}</h2>
            {tables && (
              <p className="meta">
                XER {tables.xer.version} · exported {tables.xer.export_date} · decoded as {tables.xer.encoding} · {fmt(tables.xer.line_count)} lines ·{' '}
                {tables.tables.length} tables
                {tables.broken_row_count > 0 && <> · {fmt(tables.broken_row_count)} rows quarantined and not shown here</>}
              </p>
            )}
          </div>
          <button className="close" onClick={onClose} aria-label="Close preview">Close</button>
        </header>

        {error && <div className="error" role="alert"><b>Could not load the preview.</b> {error}</div>}

        <div className="modal-body">
          <nav className="tables" aria-label="tables in the file">
            {tables?.tables.map((t) => (
              <button key={t.name} className={`tab ${t.name === table ? 'active' : ''}`} onClick={() => pick(t.name)}>
                <span className="mono">{t.name}</span>
                <small>{fmt(t.rows)} × {t.columns}</small>
              </button>
            ))}
          </nav>

          <section className="rows">
            {page && (
              <>
                <div className="pager">
                  <span className="mono">{page.table}</span>
                  <span className="dim">rows {fmt(from)}–{fmt(to)} of {fmt(total)}{loading ? ' · loading…' : ''}</span>
                  <span className="pager-btns">
                    <button disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
                    <button disabled={to >= total || loading} onClick={() => setOffset(offset + PAGE)}>Next</button>
                  </span>
                </div>
                <div className="grid-wrap">
                  {page.fields.length === 0 ? (
                    <p className="none dim">This table has no field list, so no rows were kept.</p>
                  ) : (
                    <table className="grid">
                      <thead>
                        <tr>
                          <th className="num sticky">line</th>
                          {page.fields.map((f) => <th key={f}>{f}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {page.rows.map((row, i) => (
                          <tr key={page.lines[i] ?? i}>
                            <td className="num dim sticky">{page.lines[i]}</td>
                            {row.map((v, j) => <td key={j} title={v}>{v === '' ? <span className="blank">·</span> : v}</td>)}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </>
            )}
            {!page && !error && <p className="dim">Loading…</p>}
          </section>
        </div>
      </div>
    </div>
  )
}
