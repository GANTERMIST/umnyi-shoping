import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, type CatalogItem, type GameCard, type Offer } from '../api'
import { GameTile } from '../components/GameTile'
import { useApp } from '../store'
import { OfferTable } from '../components/OfferTable'
import { PriceChart } from '../components/PriceChart'
import { Recommend } from '../components/Recommend'
import { DEFAULT_KINDS, KIND_HINT, KIND_LABEL, rub } from '../util'

export default function GamePage() {
  const { appid } = useParams()
  const [card, setCard] = useState<GameCard | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [sel, setSel] = useState<Offer | null>(null)
  const [all, setAll] = useState(false)
  const [similar, setSimilar] = useState<CatalogItem[]>([])
  const { addViewed } = useApp()

  useEffect(() => {
    setCard(null)
    setErr(null)
    api.game(Number(appid)).then(c => {
      setCard(c)
      addViewed({ appid: c.game.appid, name: c.game.name, image: c.game.image, genres: c.game.genres })
      api.similar(c.game.appid).then(setSimilar).catch(() => setSimilar([]))
      setSel(c.best['ключ'] || c.best['гифт'] || c.best['магазин'] || c.offers[0] || null)
    }).catch(e => setErr(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appid])

  if (err) return <div className="error">{err}</div>
  if (!card) return <div className="loading"><span className="spinner" /> Загружаем игру и цены во всех магазинах…</div>

  const g = card.game
  const offers = all ? card.offers : card.offers.filter(o => DEFAULT_KINDS.includes(o.kind))
  const bestKinds = ['ключ', 'гифт', 'магазин', 'аккаунт'].filter(k => card.best[k])

  return (
    <>
      <div className="game-head card">
        {g.image && <img src={g.image} alt="" />}
        <div>
          <h1>{g.name}</h1>
          <p className="muted">{g.genres.join(', ')}{g.release ? ` · выход: ${g.release}` : ''}</p>
          <div className="stats">
            {g.metacritic != null && <span className="stat"><b>{g.metacritic}</b> Metacritic</span>}
            {g.steam_review_pct != null && <span className="stat"><b>{g.steam_review_pct}%</b> положительных из {g.steam_reviews?.toLocaleString('ru-RU')} отзывов Steam</span>}
            <span className="stat"><b>{card.offers.length}</b> предложений</span>
          </div>
        </div>
      </div>

      <h2>Лучшая цена по типам</h2>
      <div className="best-grid">
        {bestKinds.map(k => {
          const o = card.best[k]
          return (
            <button key={k} className={`best card ${sel?.id === o.id ? 'sel' : ''}`} onClick={() => setSel(o)} title={KIND_HINT[k]}>
              <span className={`kind k-${k}`}>{KIND_LABEL[k]}</span>
              <span className="big-price">{rub(o.price)}</span>
              <span className="muted small ellipsis">{o.kind === 'магазин' ? o.store : o.seller} · {o.platform}</span>
            </button>
          )
        })}
        {!bestKinds.length && <p className="muted">Надёжных предложений сейчас нет.</p>}
      </div>

      <Recommend offers={card.offers} where="game" query={g.name} />

      {sel && <div className="card"><PriceChart offerId={sel.id} title={`${KIND_LABEL[sel.kind]} · ${sel.kind === 'магазин' ? sel.store : sel.seller}`} /></div>}

      <div className="sec-head">
        <h2>Все предложения</h2>
        <label className="check inline"><input type="checkbox" checked={all} onChange={e => setAll(e.target.checked)} /> Показать аккаунты и прочее</label>
      </div>
      <p className="muted small">Нажмите на строку — график цены покажет историю этого предложения.</p>
      <OfferTable offers={offers} appid={g.appid} onSelect={setSel} selected={sel?.id} />
      {similar.length > 0 && (
        <section>
          <h2>Похожие игры</h2>
          <div className="tiles">{similar.map(s => <GameTile key={s.appid} g={s} />)}</div>
        </section>
      )}
    </>
  )
}
