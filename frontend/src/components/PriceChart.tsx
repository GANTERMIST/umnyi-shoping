import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { money } from '../util'

type Pt = { ts: string; price: number }
const PERIODS = [30, 90, 365] as const

/** История цены (Ф12): одна тонкая линия, текущая цена и изменение, минимум/максимум одной строкой.
 *  Наведение показывает цену и дату в шапке — без подписей поверх графика. SVG без библиотек. */
export function PriceChart({ offerId, title, currency = 'RUB' }: { offerId: string; title: string; currency?: string }) {
  const fmtMoney = (x: number) => money(x, currency)
  const [pts, setPts] = useState<Pt[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [hover, setHover] = useState<number | null>(null)
  const [days, setDays] = useState<(typeof PERIODS)[number]>(30)

  useEffect(() => {
    setPts(null)
    setErr(null)
    api.history(offerId).then(r => setPts(r.points)).catch(e => setErr(e.message))
  }, [offerId])

  // точки периода + цена на его начало + «сейчас»: цена держится до следующего замера
  const data = useMemo(() => {
    if (!pts?.length) return []
    const now = Date.now(), from = now - days * 86400e3
    const inside = pts.filter(p => new Date(p.ts).getTime() >= from)
    const before = pts.filter(p => new Date(p.ts).getTime() < from).pop()
    const out: Pt[] = [...(before ? [{ ts: new Date(from).toISOString(), price: before.price }] : []), ...inside]
    const last = out[out.length - 1] ?? pts[pts.length - 1]
    return [...out, { ts: new Date(now).toISOString(), price: last.price }]
  }, [pts, days])

  if (err) return <p className="error">{err}</p>
  if (!pts) return <div className="skeleton" style={{ height: 140 }} />

  const periods = (
    <div className="periods" role="group" aria-label="Период">
      {PERIODS.map(d => <button key={d} className={d === days ? 'on' : ''} onClick={() => setDays(d)}>{d} дн</button>)}
    </div>
  )
  if (!pts.length) return <div className="chart"><div className="chart-head"><span className="chart-title">{title}</span>{periods}</div>
    <p className="muted small">Истории пока нет — она начнётся с первого замера.</p></div>

  const W = 640, H = 120, PAD = 4
  const xs = data.map(p => new Date(p.ts).getTime())
  const ys = data.map(p => p.price)
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)]
  let [y0, y1] = [Math.min(...ys), Math.max(...ys)]
  if (y0 === y1) { y0 *= 0.95; y1 *= 1.05 }
  const X = (t: number) => ((t - x0) / (x1 - x0 || 1)) * W
  const Y = (v: number) => PAD + (1 - (v - y0) / (y1 - y0)) * (H - 2 * PAD)
  const path = data.map((p, i) => (i === 0 ? `M${X(xs[i])},${Y(p.price)}` : `H${X(xs[i])}V${Y(p.price)}`)).join('')
  const fmtDate = (ts: string) => new Date(ts).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })

  const cur = ys[ys.length - 1], first = ys[0]
  const diff = first ? Math.round(((cur - first) / first) * 100) : 0
  const h = hover != null ? data[hover] : null
  const shown = h ?? data[data.length - 1]

  // ближайшая точка к курсору
  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const t = x0 + ((e.clientX - r.left) / r.width) * (x1 - x0)
    let i = 0
    while (i + 1 < xs.length && xs[i + 1] <= t) i++
    setHover(i)
  }

  return (
    <figure className="chart">
      <div className="chart-head">
        <div>
          <div className="chart-title">{title}</div>
          <div className="chart-now">
            <b>{fmtMoney(shown.price)}</b>
            <span className="muted">{h ? fmtDate(h.ts) : diff === 0 ? 'без изменений' : <span className={diff < 0 ? 'ok' : 'warn'}>{diff > 0 ? '+' : ''}{diff}% за {days} дн</span>}</span>
          </div>
        </div>
        {periods}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
        aria-label={`График цены, сейчас ${fmtMoney(cur)}`} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        <path d={path} className="line" vectorEffect="non-scaling-stroke" />
        {h && <line x1={X(xs[hover!])} x2={X(xs[hover!])} y1={0} y2={H} className="cursor" vectorEffect="non-scaling-stroke" />}
      </svg>
      <div className="chart-foot">
        <span>{fmtDate(data[0].ts)}</span>
        <span>мин {fmtMoney(Math.min(...ys))} · макс {fmtMoney(Math.max(...ys))}</span>
        <span>сегодня</span>
      </div>
    </figure>
  )
}
