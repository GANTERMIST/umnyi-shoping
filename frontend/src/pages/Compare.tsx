import { Link } from 'react-router-dom'
import type { Offer } from '../api'
import { useApp } from '../store'
import { compareVerdict, delivery, guarantee, KIND_LABEL, price, regionText, trustLabel } from '../util'
import { Feedback } from '../components/Feedback'

export default function Compare() {
  const { compare, toggleCompare, clearCompare, profile } = useApp()
  if (!compare.length) {
    return (
      <div className="empty">
        <h2>Сравнивать пока нечего</h2>
        <p className="muted">Отметьте «Сравнить» у 2–4 предложений в поиске или карточке игры.</p>
        <Link to="/catalog" className="btn">В каталог</Link>
      </div>
    )
  }
  // «лучше» по цене — только среди цен одной валюты (рубли с долларами не сравниваем)
  const rubPrices = compare.filter(o => o.currency === 'RUB').map(o => o.price)
  const minCur = rubPrices.length ? 'RUB' : 'USD'
  const minPrice = Math.min(...compare.filter(o => o.currency === minCur).map(o => o.price))
  const maxTrust = Math.max(...compare.map(o => o.trust_score))
  const rows: { label: string; get: (o: Offer) => React.ReactNode; best?: (o: Offer) => boolean }[] = [
    { label: 'Цена', get: o => <b>{price(o)}</b>, best: o => o.currency === minCur && o.price === minPrice },
    { label: 'Тип', get: o => KIND_LABEL[o.kind] },
    { label: 'Платформа', get: o => o.platform },
    { label: 'Магазин', get: o => o.store },
    { label: 'Продавец', get: o => o.seller },
    { label: 'Регион', get: o => regionText(o, profile.region) },
    { label: 'Доставка', get: o => delivery(o) },
    { label: 'Возврат и гарантия', get: o => guarantee(o) },
    { label: 'Надёжность', get: o => trustLabel(o), best: o => o.trust_score === maxTrust },
    { label: 'Отзывы', get: o => (o.kind === 'магазин' ? '—' : `+${o.reviews_pos} / −${o.reviews_neg}`) },
    { label: 'Продано', get: o => (o.kind === 'магазин' ? '—' : o.sold.toLocaleString('ru-RU')) },
  ]
  return (
    <>
      <div className="sec-head">
        <h1>Сравнение ({compare.length} / 4)</h1>
        <button className="btn ghost" onClick={clearCompare}>Очистить</button>
      </div>
      {compare.length > 1 && (
        <div className="recommend card">
          <span className="rec-label">Вывод</span>
          <ul className="verdict">{compareVerdict(compare, profile.region).map(t => <li key={t}>{t}</li>)}</ul>
          <Feedback where="compare" query={compare.map(o => o.id).sort().join(',')} />
        </div>
      )}
      <div className="table-wrap">
        <table className="compare">
          <thead>
            <tr>
              <th />
              {compare.map(o => (
                <th key={o.id}>
                  <div className="cmp-title">{o.title}</div>
                  <button className="btn small ghost" onClick={() => toggleCompare(o)}>Убрать</button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.label}>
                <th scope="row">{r.label}</th>
                {compare.map(o => <td key={o.id} className={r.best?.(o) ? 'best-cell' : ''}>{r.get(o)}</td>)}
              </tr>
            ))}
            <tr>
              <th />
              {compare.map(o => <td key={o.id}><a className="btn primary small" href={o.url} target="_blank" rel="noopener noreferrer">Купить ↗</a></td>)}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="muted small">Зелёным отмечены лучшие значения. Цены сохранены в момент добавления к сравнению.</p>
    </>
  )
}
