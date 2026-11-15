import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { money } from '../util'

type Pt = { ts: string; price: number }
const PERIODS = [30, 90, 365] as const

/** История цены за 30 / 90 / 365 дней (Ф12): ступенчатый график до «сейчас», минимум и максимум. SVG без библиотек. */
export function PriceChart({ offerId, title, currency = 'RUB' }: { offerId: string; title: string; currency?: string }) {
  const rub = (x: number) => money(x, currency)  // подписи в валюте предложения
  const [pts, setPts] = useState<Pt[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [hover, setHover] = useState<number | null>(null)
  const [days, setDays] = useState<(typeof PERIODS)[number]>(30)

  useEffect(() => {
    setPts(null)
    setErr(null)
    api.history(offerId).then(r => setPts(r.points)).catch(e => setErr(e.message))
  }, [offerId])

  // точки периода + цена на его начало + «сейчас» справа: цена держится до следующего замера
  const data = useMemo(() => {
    if (!pts?.length) return []
    const now = Date.now(), from = now - days * 86400e3
    const inside = pts.filter(p => new Date(p.ts).getTime() >= from)
    const before = pts.filter(p => new Date(p.ts).getTime() < from).pop()
    const out: Pt[] = [...(before ? [{ ts: new Date(from).toISOString(), price: before.price }] : []), ...inside]
    const last = out[out.length - 1] ?? pts[pts.length - 1]
    return [...out, { ts: new Date(now).toISOString(), price: last.price }]
  }, [pts, days])

  const head = (
    <div className="chart-head">
      <span>История цены: <b>{title}</b></span>
      <div className="periods" role="group" aria-label="Период">
        {PERIODS.map(d => <button key={d} className={d === days ? 'on' : ''} onClick={() => setDays(d)}>{d}Д</button>)}
      </div>
    </div>
  )
  if (err) return <p className="error">{err}</p>
  if (!pts) return <div className="skeleton" style={{ height: 200 }} />
  if (!pts.length) return <>{head}<p className="muted">Истории пока нет: она начнётся с первого замера цены.</p></>

  const W = 640, H = 200, P = { l: 70, r: 16, t: 16, b: 28 }
  const xs = data.map(p => new Date(p.ts).getTime())
  const ys = data.map(p => p.price)
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)]
  let [y0, y1] = [Math.min(...ys), Math.max(...ys)]
  if (y0 === y1) { y0 *= 0.9; y1 *= 1.1 }
  const X = (t: number) => P.l + ((t - x0) / (x1 - x0 || 1)) * (W - P.l - P.r)
  const Y = (v: number) => P.t + (1 - (v - y0) / (y1 - y0)) * (H - P.t - P.b)
  const path = data.map((p, i) => (i === 0 ? `M${X(xs[i])},${Y(p.price)}` : `H${X(xs[i])}V${Y(p.price)}`)).join('')
  const fmt = (ts: string) => new Date(ts).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
  const marks = data.slice(0, -1)  // реальные замеры (последняя точка — «сейчас»)
  const h = hover != null ? marks[hover] : null

  return (
    <figure className="chart">
      {head}
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`График цены, сейчас ${rub(ys[ys.length - 1])}`}
        onMouseLeave={() => setHover(null)}>
        {[y0, (y0 + y1) / 2, y1].map((t, i) => (
          <g key={i}>
            <line x1={P.l} x2={W - P.r} y1={Y(t)} y2={Y(t)} className="grid" />
            <text x={P.l - 10} y={Y(t) + 4} textAnchor="end" className="axis">{rub(t)}</text>
          </g>
        ))}
        <text x={P.l} y={H - 6} className="axis">{fmt(data[0].ts)}</text>
        <text x={W - P.r} y={H - 6} textAnchor="end" className="axis">сегодня</text>
        <path d={path} className="line" />
        {marks.map((p, i) => (
          <circle key={i} cx={X(xs[i])} cy={Y(p.price)} r={hover === i ? 5 : 3.5} className="dot" onMouseEnter={() => setHover(i)} />
        ))}
        {h && (
          <text x={Math.min(X(xs[hover!]) + 8, W - 170)} y={Math.max(Y(h.price) - 10, 14)} className="tip">
            {rub(h.price)}, {new Date(h.ts).toLocaleDateString('ru-RU')}
          </text>
        )}
      </svg>
      <div className="minmax">
        <div>Мин. за {days} дн.<b>{rub(Math.min(...ys))}</b></div>
        <div>Макс. за {days} дн.<b>{rub(Math.max(...ys))}</b></div>
      </div>
      {pts.length === 1 && <p className="tiny">Пока один замер: цена не менялась с {fmt(pts[0].ts)}.</p>}
    </figure>
  )
}
