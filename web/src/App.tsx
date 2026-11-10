import { useCallback, useEffect, useRef, useState } from 'react'
import {
  checkSample,
  checkUpload,
  listSamples,
  type BrokenRow,
  type CheckName,
  type CheckResponse,
  type Finding,
  type Sample,
} from './api'

const CHECKS: { key: CheckName; label: string; blurb: string }[] = [
  { key: 'missing_links', label: 'Missing links', blurb: 'Activities with no predecessor, no successor, or neither. Level-of-effort and WBS summary activities are skipped.' },
  { key: 'negative_float', label: 'Negative float', blurb: 'Total float below zero. The activity is already late against a constraint or must-finish date.' },
  { key: 'high_float', label: 'High float', blurb: 'Total float above the threshold. Usually means the activity is not properly tied into the network.' },
]

const SAMPLE_LABELS: Record<string, string> = {
  'terminal-building-airport.xer': 'Airport terminal',
  'hotel-project.xer': 'Hotel programme',
  'planted-defects.xer': 'Planted defects',
}

const fmt = (n: number) => n.toLocaleString('en-US')
const kb = (b: number) => (b > 1024 * 1024 ? `${(b / 1024 / 1024).toFixed(1)} MB` : `${Math.round(b / 1024)} KB`)

export default function App() {
  const [samples, setSamples] = useState<Sample[]>([])
  const [threshold, setThreshold] = useState(44)
  const [result, setResult] = useState<CheckResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const lastSource = useRef<{ kind: 'sample'; name: string } | { kind: 'file'; file: File } | null>(null)

  useEffect(() => {
    listSamples().then(setSamples).catch((e: Error) => setError(e.message))
  }, [])

  const run = useCallback(
    async (source: { kind: 'sample'; name: string } | { kind: 'file'; file: File }, days: number) => {
      lastSource.current = source
      setBusy(source.kind === 'sample' ? source.name : source.file.name)
      setError(null)
      try {
        const r = source.kind === 'sample' ? await checkSample(source.name, days) : await checkUpload(source.file, days)
        setResult(r)
      } catch (e) {
        setResult(null)
        setError((e as Error).message)
      } finally {
        setBusy(null)
      }
    },
    [],
  )

  // Re-run the current file when the threshold changes (debounced).
  useEffect(() => {
    if (!lastSource.current || !result) return
    if (result.high_float_threshold_days === threshold) return
    const t = setTimeout(() => run(lastSource.current!, threshold), 350)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threshold])

  const onFiles = (files: FileList | null) => {
    const f = files?.[0]
    if (f) run({ kind: 'file', file: f }, threshold)
  }

  return (
    <div className="page">
      <header className="masthead">
        <div>
          <h1>p6checker</h1>
          <p>Reads a Primavera P6 .xer export, quarantines rows it cannot trust, and runs three schedule-health checks.</p>
        </div>
        <a className="quiet" href="/docs" target="_blank" rel="noreferrer">API docs</a>
      </header>

      <section className="intake">
        <label
          className={`drop ${dragging ? 'drop-active' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); onFiles(e.dataTransfer.files) }}
        >
          <input type="file" accept=".xer" onChange={(e) => { onFiles(e.target.files); e.target.value = '' }} />
          <span className="drop-title">Drop a .xer file here, or click to choose one</span>
          <span className="drop-sub">Files stay on this machine. Up to 50 MB.</span>
        </label>

        <div className="samples">
          <span className="eyebrow">Or check a bundled schedule</span>
          <div className="sample-row">
            {samples.map((s) => (
              <button key={s.name} className={`sample ${s.kind}`} disabled={busy !== null} onClick={() => run({ kind: 'sample', name: s.name }, threshold)}>
                <b>{SAMPLE_LABELS[s.name] ?? s.name}</b>
                <small>{s.name} · {kb(s.bytes)}{s.kind === 'fixture' ? ' · hand-written, every defect planted' : ' · real P6 export'}</small>
              </button>
            ))}
          </div>
          <label className="threshold">
            High float above
            <input type="number" min={1} max={999} value={threshold} onChange={(e) => setThreshold(Math.max(1, Number(e.target.value) || 1))} />
            working days
          </label>
        </div>
      </section>

      {busy && <p className="status" role="status">Checking {busy}…</p>}
      {error && (
        <div className="error" role="alert">
          <b>Could not check this file.</b> {error}
        </div>
      )}
      {result && !busy && <Results r={result} />}
      {!result && !busy && !error && (
        <p className="empty">Nothing checked yet. Drop a file or pick a bundled schedule above.</p>
      )}
    </div>
  )
}

function Results({ r }: { r: CheckResponse }) {
  const top = useRef<HTMLElement>(null)
  useEffect(() => {
    top.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [r.file])
  const scheduled = r.activity_count - r.unscheduled_count
  const neg = r.counts.negative_float
  const high = r.counts.high_float
  const ok = scheduled - neg - high
  const projects = r.xer.projects.map((p) => p.short_name).join(', ')

  return (
    <main className="results" ref={top}>
      <div className="filehead">
        <h2>{r.file}</h2>
        <p className="meta">
          XER {r.xer.version} · exported {r.xer.export_date} · decoded as {r.xer.encoding} · {fmt(r.xer.line_count)} lines
          {projects && <> · projects: {projects}</>}
        </p>
      </div>

      <div className="tiles">
        <Tile label="activities checked" value={r.activity_count} />
        <Tile label="relationships" value={r.xer.relationship_count} />
        <Tile label="broken rows quarantined" value={r.broken_rows.length} tone={r.broken_rows.length ? 'bad' : 'ok'} />
        <Tile label="missing links" value={r.counts.missing_links} tone={r.counts.missing_links ? 'bad' : 'ok'} />
        <Tile label="negative float" value={neg} tone={neg ? 'bad' : 'ok'} />
        <Tile label={`high float > ${r.high_float_threshold_days} d`} value={high} tone={high ? 'warn' : 'ok'} />
      </div>

      <section className="band-wrap">
        <div className="eyebrow">Where the float sits · {fmt(scheduled)} scheduled activities</div>
        <div className="band" aria-label="float bands">
          {neg > 0 && <span className="seg neg" style={{ flex: neg }} title={`negative: ${neg}`} />}
          {ok > 0 && <span className="seg ok" style={{ flex: ok }} title={`0 to ${r.high_float_threshold_days} days: ${ok}`} />}
          {high > 0 && <span className="seg high" style={{ flex: high }} title={`above ${r.high_float_threshold_days} days: ${high}`} />}
        </div>
        <div className="band-legend">
          <span><i className="sw neg" />negative {fmt(neg)}</span>
          <span><i className="sw ok" />0 to {r.high_float_threshold_days} days {fmt(ok)}</span>
          <span><i className="sw high" />above {r.high_float_threshold_days} days {fmt(high)}</span>
          {r.unscheduled_count > 0 && <span className="quiet">{fmt(r.unscheduled_count)} never scheduled, excluded</span>}
        </div>
      </section>

      <figure className="chart">
        <img src={`data:image/png;base64,${r.chart_png_base64}`} alt={`Total float distribution for ${r.file}`} />
      </figure>

      {CHECKS.map((c) => (
        <FindingsSection key={c.key} title={c.key === 'high_float' ? `${c.label} (above ${r.high_float_threshold_days} working days)` : c.label} blurb={c.blurb} rows={r.findings[c.key]} />
      ))}

      <BrokenSection rows={r.broken_rows} lineCount={r.xer.line_count} />
    </main>
  )
}

function Tile({ label, value, tone }: { label: string; value: number; tone?: 'ok' | 'bad' | 'warn' }) {
  return (
    <div className={`tile ${tone ?? ''}`}>
      <span>{label}</span>
      <b>{fmt(value)}</b>
    </div>
  )
}

const PAGE = 100

function FindingsSection({ title, blurb, rows }: { title: string; blurb: string; rows: Finding[] }) {
  const [all, setAll] = useState(false)
  const shown = all ? rows : rows.slice(0, PAGE)
  return (
    <section className="block">
      <h3>{title} <span className="count">{fmt(rows.length)}</span></h3>
      <p className="blurb">{blurb}</p>
      {rows.length === 0 ? (
        <p className="none">None found.</p>
      ) : (
        <>
          <table>
            <thead><tr><th>Activity</th><th>Name</th><th>Type</th><th>Detail</th><th className="num">Line</th></tr></thead>
            <tbody>
              {shown.map((f) => (
                <tr key={`${f.task_code}-${f.line}`}>
                  <td className="mono">{f.task_code}</td>
                  <td>{f.task_name}</td>
                  <td className="mono dim">{f.task_type.replace('TT_', '')}</td>
                  <td>{f.detail}</td>
                  <td className="num mono dim">{f.line}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > PAGE && (
            <button className="more" onClick={() => setAll(!all)}>{all ? `Show first ${PAGE}` : `Show all ${fmt(rows.length)}`}</button>
          )}
        </>
      )}
    </section>
  )
}

function BrokenSection({ rows, lineCount }: { rows: BrokenRow[]; lineCount: number }) {
  return (
    <section className="block">
      <h3>Broken rows quarantined <span className="count">{fmt(rows.length)}</span></h3>
      <p className="blurb">Rows that could not be trusted were excluded from every check rather than guessed at. Each one is reported with its line number and the reason.</p>
      {rows.length === 0 ? (
        <p className="none">Every row in this file parsed cleanly.</p>
      ) : (
        <>
          <div className="ruler" aria-label="position of broken rows in the file">
            {rows.map((b, i) => (
              <i key={i} style={{ left: `${(100 * Math.max(0, b.line - 1)) / Math.max(1, lineCount - 1)}%` }} title={`line ${b.line}: ${b.reason}`} />
            ))}
            <span className="ruler-l">line 1</span>
            <span className="ruler-r">line {fmt(lineCount)}</span>
          </div>
          <table>
            <thead><tr><th className="num">Line</th><th>Table</th><th>Reason</th><th>Raw (truncated)</th></tr></thead>
            <tbody>
              {rows.map((b, i) => (
                <tr key={i}>
                  <td className="num mono">{b.line}</td>
                  <td className="mono dim">{b.table ?? '–'}</td>
                  <td>{b.reason}</td>
                  <td className="mono raw">{b.raw}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}
