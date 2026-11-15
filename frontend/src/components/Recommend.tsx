import { Link } from 'react-router-dom'
import type { Offer } from '../api'
import { useApp } from '../store'
import { delivery, KIND_LABEL, recommend, rub } from '../util'
import { Feedback } from './Feedback'

/** Блок «Рекомендуем вам»: лучшее предложение под профиль с объяснением выбора. */
export function Recommend({ offers, where = 'search', query }: { offers: Offer[]; where?: 'search' | 'game'; query?: string }) {
  const { profile, toggleFav, isFav, favorites } = useApp()
  const rec = recommend(offers, profile, favorites)
  const custom = profile.budget || profile.platform || profile.kinds.length
  if (!rec) return null
  const o = rec.offer
  return (
    <div className="recommend card">
      <div className="rec-head">
        <span className="rec-label">★ Рекомендуем вам</span>
        {!custom && <Link to="/profile" className="small">Укажите бюджет и платформу в профиле — подбор станет точнее</Link>}
      </div>
      {rec.relaxed && <p className="warn small">{rec.relaxed}</p>}
      <div className="rec-body">
        <div>
          <div className="rec-title">{o.title}</div>
          <div className="muted small">{KIND_LABEL[o.kind]} · {o.platform} · {o.kind === 'магазин' ? o.store : `продавец ${o.seller}`} · {delivery(o)}</div>
          <ul className="reasons">{rec.reasons.map(r => <li key={r}>✓ {r}</li>)}</ul>
        </div>
        <div className="rec-buy">
          <div className="big-price">{rub(o.price)}</div>
          <a className="btn primary" href={o.url} target="_blank" rel="noopener noreferrer">Купить у продавца →</a>
          <button className="btn ghost small" onClick={() => toggleFav(o)}>{isFav(o.id) ? '♥ Отслеживаю' : '♡ Следить за ценой'}</button>
        </div>
      </div>
      <Feedback where={where} offerId={o.id} query={query} />
    </div>
  )
}
