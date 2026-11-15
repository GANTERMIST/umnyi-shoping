import { Link } from 'react-router-dom'
import type { CatalogItem } from '../api'
import { KIND_LABEL, rub } from '../util'

export function GameTile({ g }: { g: CatalogItem }) {
  return (
    <Link to={`/game/${g.appid}`} className="tile">
      {g.image ? <img src={g.image} alt="" loading="lazy" /> : <div className="noimg" />}
      <div className="tile-body">
        <div className="tile-title">{g.name}</div>
        <div className="tile-price">
          <b>{rub(g.best_price)}</b>
          {g.best_kind && <span className="muted small"> · {KIND_LABEL[g.best_kind]}</span>}
          {g.savings_pct ? <span className="save">−{g.savings_pct}%</span> : null}
        </div>
        <div className="muted small">
          {g.official_price ? `офиц. ${rub(g.official_price)} · ` : ''}{g.offers} предл.
          {g.steam_review_pct != null && ` · ${g.steam_review_pct}% 👍`}
        </div>
      </div>
    </Link>
  )
}

export function Skeletons({ n = 4 }: { n?: number }) {
  return <div className="tiles">{Array.from({ length: n }, (_, i) => <div key={i} className="skeleton tile-sk" />)}</div>
}
