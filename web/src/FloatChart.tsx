import { useMemo, useState } from 'react'
import type { BinActivity, FloatGroup, Histogram } from './api'

const GROUPS: { key: FloatGroup; label: (thr: number) => string; color: string }[] = [
  { key: 'negative', label: () => 'negative', color: 'var(--neg)' },
  { key: 'ok', label: (thr) => `0 to ${fmtNum(thr)} d`, color: 'var(--ok)' },
  { key: 'high', label: (thr) => `above ${fmtNum(thr)} d`, color: 'var(--high)' },
]

const W = 960
const H = 360
const PAD = { top: 28, right: 24, bottom: 56, left: 56 }
const GAP = 2 // px of surface between stacked segments and between bars

function fmtNum(n: number) {
  return Number.isInteger(n) ? n.toLocaleString('en-US') : n.toFixed(1)
}

/** Stacked histogram of total float. Hover or focus a bar for its range and
 *  counts; click it to list the activities behind it. Bars are SVG rects drawn
 *  from the same bins as the PNG report, so the two never disagree. */
export default function FloatChart({ file, histogram }: { file: string; histogram: Histogram }) {
  const { bins, threshold } = histogram
  const [hover, setHover] = useState<number | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [showAll, setShowAll] = useState(false)

  const x0 = bins.length ? bins[0].lo : 0
  const x1 = bins.length ? bins[bins.length - 1].hi : 1
  const maxCount = Math.max(1, ...bins.map((b) => b.negative + b.ok + b.high))
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const sx = (v: number) => PAD.left + ((v - x0) / (x1 - x0)) * innerW
  const sy = (c: number) => PAD.top + innerH - (c / maxCount) * innerH

  const xTicks = useMemo(() => niceTicks(x0, x1, 8), [x0, x1])
  const yTicks = useMemo(() => niceTicks(0, maxCount, 5).filter((t) => Number.isInteger(t)), [maxCount])
  const totals = { negative: 0, ok: 0, high: 0 }
  for (const b of bins) { totals.negative += b.negative; totals.ok += b.ok; totals.high += b.high }

  if (!bins.length) {
    return <p className="none dim">No scheduled activities, so there is no float to chart.</p>
  }

  const active = hover ?? selected
  const activeBin = active !== null ? bins[active] : null
  const selBin = selected !== null ? bins[selected] : null
  const listed = selBin ? (showAll ? selBin.activities : selBin.activities.slice(0, 100)) : []

  return (
    <div className="fchart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Total float per activity in ${file}`} className="fchart-svg">
        {/* grid + y axis */}
        {yTicks.map((t) => (
          <g key={`y${t}`}>
            <line x1={PAD.left} x2={W - PAD.right} y1={sy(t)} y2={sy(t)} className="grid" />
            <text x={PAD.left - 8} y={sy(t)} className="tick" textAnchor="end" dominantBaseline="middle">{t.toLocaleString('en-US')}</text>
          </g>
        ))}
        {/* x axis */}
        <line x1={PAD.left} x2={W - PAD.right} y1={PAD.top + innerH} y2={PAD.top + innerH} className="axis" />
        {xTicks.map((t) => (
          <text key={`x${t}`} x={sx(t)} y={PAD.top + innerH + 18} className="tick" textAnchor="middle">{t.toLocaleString('en-US')}</text>
        ))}
        <text x={PAD.left + innerW / 2} y={H - 10} className="axis-label" textAnchor="middle">total float (working days, per activity calendar)</text>
        <text transform={`translate(14 ${PAD.top + innerH / 2}) rotate(-90)`} className="axis-label" textAnchor="middle">activities</text>

        {/* bars */}
        {bins.map((b, i) => {
          const left = sx(b.lo) + GAP / 2
          const width = Math.max(1, sx(b.hi) - sx(b.lo) - GAP)
          const total = b.negative + b.ok + b.high
          let yTop = sy(0)
          const segs = (['negative', 'ok', 'high'] as FloatGroup[]).filter((g) => b[g] > 0).map((g) => {
            const h = (b[g] / maxCount) * innerH
            const y = yTop - h
            yTop = y - GAP
            return { g, y, h: Math.max(0, h - (b[g] === total ? 0 : 0)) }
          })
          const isActive = active === i
          const label = `${fmtNum(b.lo)} to ${fmtNum(b.hi)} days: ${total} activities` +
            (b.negative ? `, ${b.negative} negative` : '') + (b.ok ? `, ${b.ok} within threshold` : '') + (b.high ? `, ${b.high} above threshold` : '')
          return (
            <g
              key={i}
              className={`bar ${isActive ? 'active' : ''} ${selected === i ? 'selected' : ''}`}
              tabIndex={total ? 0 : -1}
              role={total ? 'button' : undefined}
              aria-label={total ? label : undefined}
              aria-pressed={total ? selected === i : undefined}
              pointerEvents={total ? 'auto' : 'none'}
              onPointerEnter={() => total && setHover(i)}
              onPointerLeave={() => setHover(null)}
              onFocus={() => total && setHover(i)}
              onBlur={() => setHover(null)}
              onClick={() => { if (!total) return; setSelected(selected === i ? null : i); setShowAll(false) }}
              onKeyDown={(e) => { if (total && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); setSelected(selected === i ? null : i); setShowAll(false) } }}
            >
              {/* hit target: the full column, bigger than the painted bar */}
              <rect x={sx(b.lo)} y={PAD.top} width={Math.max(1, sx(b.hi) - sx(b.lo))} height={innerH} className="hit" />
              {segs.map((s) => (
                <rect key={s.g} x={left} y={s.y} width={width} height={s.h} rx={s.y === segs[segs.length - 1].y ? 3 : 0} className={`seg-${s.g}`} />
              ))}
            </g>
          )
        })}

        {/* threshold lines, drawn above the bars */}
        <line x1={sx(0)} x2={sx(0)} y1={PAD.top - 6} y2={PAD.top + innerH} className="rule rule-neg" />
        <text x={sx(0) - 5} y={PAD.top - 10} className="rule-text rule-neg-t" textAnchor="end">0 d</text>
        <line x1={sx(threshold)} x2={sx(threshold)} y1={PAD.top - 6} y2={PAD.top + innerH} className="rule rule-high" />
        <text x={sx(threshold) + 5} y={PAD.top - 10} className="rule-text rule-high-t">high float &gt; {fmtNum(threshold)} d</text>

        {/* tooltip */}
        {activeBin && (
          <Tooltip bin={activeBin} x={sx((activeBin.lo + activeBin.hi) / 2)} y={sy(activeBin.negative + activeBin.ok + activeBin.high)} threshold={threshold} />
        )}
      </svg>

      <div className="fchart-legend" aria-hidden="true">
        {GROUPS.map((g) => (
          <span key={g.key}><i className="sw" style={{ background: g.color }} />{g.label(threshold)} <b>{totals[g.key].toLocaleString('en-US')}</b></span>
        ))}
        <span className="dim">hover a bar for its range · click to list its activities</span>
      </div>

      {selBin && (
        <div className="fchart-sel">
          <div className="fchart-sel-head">
            <b>{fmtNum(selBin.lo)} to {fmtNum(selBin.hi)} days</b>
            <span className="dim">{selBin.activities.length.toLocaleString('en-US')} activities</span>
            <button className="more" onClick={() => setSelected(null)}>Clear</button>
          </div>
          <table>
            <thead><tr><th>Activity</th><th>Name</th><th className="num">Float (d)</th><th>Group</th></tr></thead>
            <tbody>
              {listed.map((a: BinActivity) => (
                <tr key={a.code}>
                  <td className="mono">{a.code}</td>
                  <td>{a.name}</td>
                  <td className="num mono">{a.days.toLocaleString('en-US')}</td>
                  <td><i className={`sw sw-${a.group}`} />{a.group === 'ok' ? 'within threshold' : a.group}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {selBin.activities.length > 100 && (
            <button className="more" onClick={() => setShowAll(!showAll)}>{showAll ? 'Show first 100' : `Show all ${selBin.activities.length.toLocaleString('en-US')}`}</button>
          )}
        </div>
      )}
    </div>
  )
}

function Tooltip({ bin, x, y, threshold }: { bin: Histogram['bins'][number]; x: number; y: number; threshold: number }) {
  const rows = GROUPS.filter((g) => bin[g.key] > 0)
  const total = bin.negative + bin.ok + bin.high
  const tw = 190
  const th = 30 + rows.length * 18
  const left = Math.min(Math.max(PAD.left, x - tw / 2), W - PAD.right - tw)
  const top = Math.max(4, y - th - 10)
  return (
    <g className="tip" transform={`translate(${left} ${top})`} pointerEvents="none">
      <rect width={tw} height={th} rx={6} />
      <text x={10} y={18} className="tip-title">{fmtNum(bin.lo)} to {fmtNum(bin.hi)} d · {total} {total === 1 ? 'activity' : 'activities'}</text>
      {rows.map((g, i) => (
        <g key={g.key} transform={`translate(10 ${34 + i * 18})`}>
          <line x1={0} x2={12} y1={0} y2={0} style={{ stroke: g.color }} strokeWidth={3} />
          <text x={18} y={4} className="tip-val">{bin[g.key]}</text>
          <text x={46} y={4} className="tip-key">{g.label(threshold)}</text>
        </g>
      ))}
    </g>
  )
}

function niceTicks(lo: number, hi: number, n: number): number[] {
  const span = hi - lo || 1
  const raw = span / n
  const mag = Math.pow(10, Math.floor(Math.log10(raw)))
  const norm = raw / mag
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag
  const out: number[] = []
  for (let t = Math.ceil(lo / step) * step; t <= hi + 1e-9; t += step) out.push(Math.round(t * 1e6) / 1e6 || 0) // `|| 0` turns -0 into 0
  return out
}
