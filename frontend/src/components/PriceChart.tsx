import { useEffect, useState } from 'react'
import { api } from '../api'
import { rub } from '../util'

/** График истории цены предложения (SVG, без библиотек). */
export function PriceChart({ offerId, title }: { offerId: string; title: string }) {
  const [pts, setPts] = useState<{ ts: string; price: number }[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [hover, setHover] = useState<number | null>(null)

  useEffect(() => {
    setPts(null)
    setErr(null)
    api.history(offerId).then(r => setPts(r.points)).catch(e => setErr(e.message))
  }, [offerId])

  if (err) return <p className="error">{err}</p>
  if (!pts) return <div className="skeleton" style={{ height: 180 }} />
  if (!pts.length) return <p className="muted">Истории пока нет — цена появится после первого замера.</p>

  const W = 640, H = 200, P = { l: 64, r: 16, t: 16, b: 28 }
  // одна точка — рисуем ровную линию до «сейчас»
  const data = pts.length === 1 ? [pts[0], { ts: new Date().toISOString(), price: pts[0].price }] : pts
  const xs = data.map(p => new Date(p.ts).getTime())
  const ys = data.map(p => p.price)
  const [x0, x1] = [Math.min(...xs), Math.max(...xs) || 1]
  let [y0, y1] = [Math.min(...ys), Math.max(...ys)]
  if (y0 === y1) { y0 *= 0.9; y1 *= 1.1 }
  const X = (t: number) => P.l + ((t - x0) / (x1 - x0 || 1)) * (W - P.l - P.r)
  const Y = (v: number) => P.t + (1 - (v - y0) / (y1 - y0)) * (H - P.t - P.b)
  const path = data.map((p, i) => {
    const x = X(xs[i]), y = Y(p.price)
    if (i === 0) return `M${x},${y}`
    return `H${x}V${y}` // ступенька: цена держится до следующего замера
  }).join('')
  const ticks = [y0, (y0 + y1) / 2, y1]
  const fmt = (ts: string) => new Date(ts).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
  const h = hover != null ? data[hover] : null

  return (
    <figure className="chart">
      <figcaption>История цены: <b>{title}</b>{pts.length === 1 && <span className="muted"> · пока один замер</span>}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`График цены, сейчас ${rub(ys[ys.length - 1])}`}
        onMouseLeave={() => setHover(null)}>
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={P.l} x2={W - P.r} y1={Y(t)} y2={Y(t)} className="grid" />
            <text x={P.l - 8} y={Y(t) + 4} textAnchor="end" className="axis">{rub(t)}</text>
          </g>
        ))}
        <text x={P.l} y={H - 6} className="axis">{fmt(data[0].ts)}</text>
        <text x={W - P.r} y={H - 6} textAnchor="end" className="axis">{fmt(data[data.length - 1].ts)}</text>
        <path d={path} className="line" />
        {data.map((p, i) => (
          <circle key={i} cx={X(xs[i])} cy={Y(p.price)} r={hover === i ? 6 : 4} className="dot" onMouseEnter={() => setHover(i)} />
        ))}
        {h && (
          <text x={Math.min(X(xs[hover!]), W - 150)} y={Math.max(Y(h.price) - 12, 14)} className="tip">
            {rub(h.price)} · {new Date(h.ts).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })}
          </text>
        )}
      </svg>
    </figure>
  )
}
