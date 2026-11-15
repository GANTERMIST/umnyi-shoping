import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type CatalogItem, type GameCard, type Offer } from '../api'
import { GameTile } from '../components/GameTile'
import { OfferTable } from '../components/OfferTable'
import { PriceChart } from '../components/PriceChart'
import { Recommend } from '../components/Recommend'
import { useApp } from '../store'
import { byPrice, DEFAULT_KINDS, KIND_HINT, KIND_LABEL, price } from '../util'

export default function GamePage() {
  const { appid } = useParams()
  const [card, setCard] = useState<GameCard | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [sel, setSel] = useState<Offer | null>(null)
  const [all, setAll] = useState(false)
  const [similar, setSimilar] = useState<CatalogItem[]>([])
  const { addViewed, toggleFav, isFav } = useApp()

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
  if (!card) return <div className="loading"><span className="spinner" /> Собираю цены во всех магазинах, обычно до 10 секунд</div>

  const g = card.game
  const offers = all ? card.offers : card.offers.filter(o => DEFAULT_KINDS.includes(o.kind))
  const bestKinds = ['ключ', 'гифт', 'магазин', 'аккаунт'].filter(k => card.best[k])
  const top = DEFAULT_KINDS.map(k => card.best[k]).filter(Boolean).sort(byPrice)[0]
  const official = card.best['магазин']
  const stores = new Set(card.offers.map(o => (o.store === 'plati.market' ? `plati:${o.seller}` : o.store))).size

  return (
    <>
      <p className="product-meta" style={{ marginBottom: 12 }}>
        <Link to="/">Главная</Link> / <Link to="/catalog">Каталог</Link> / {g.name}
      </p>
      <Recommend offers={card.offers} where="game" query={g.name} />
      <section className="product">
        <div className="product-media">{g.image && <img src={g.image} alt={g.name} />}</div>
        <div className="product-info">
          <div>
            <div className="product-meta">{g.genres.join(', ')}{g.release ? ` / выход ${g.release}` : ''}</div>
            <h1>{g.name}</h1>
            <div className="stats" style={{ marginTop: 8 }}>
              {g.metacritic != null && <span className="stat">Metacritic <b>{g.metacritic}</b></span>}
              {g.steam_review_pct != null && <span className="stat">Steam <b>{g.steam_review_pct}%</b> положительных</span>}
              <span className="stat"><b>{card.offers.length}</b> предложений</span>
            </div>
          </div>
          {top && (
            <div className="product-price">
              <div className="big-price">{price(top)}</div>
              <div className="product-meta" style={{ marginTop: 8 }}>
                лучшая цена из {stores} продавцов и магазинов / {KIND_LABEL[top.kind].toLowerCase()} / {top.kind === 'магазин' ? top.store : top.seller}
                {official && official.id !== top.id ? ` / официально ${price(official)}` : ''}
              </div>
            </div>
          )}
          {top && (
            <div className="product-buy">
              <a className="btn primary" href={top.url} target="_blank" rel="noopener noreferrer">В магазин ↗</a>
              <button className="btn" onClick={() => toggleFav(top, g.appid)}>{isFav(top.id) ? 'Отслеживаю цену' : 'Следить за ценой'}</button>
            </div>
          )}
        </div>
      </section>

      <div className="sec-head"><h2>Лучшая цена по типам</h2></div>
      <div className="best-grid">
        {bestKinds.map(k => {
          const o = card.best[k]
          return (
            <button key={k} className={`best ${sel?.id === o.id ? 'sel' : ''}`} onClick={() => setSel(o)} title={KIND_HINT[k]}>
              <span className={`kind k-${k}`}>{KIND_LABEL[k]}</span>
              <span className="big-price">{price(o)}</span>
              <span className="muted small ellipsis">{o.kind === 'магазин' ? o.store : o.seller} / {o.platform}</span>
            </button>
          )
        })}
        {!bestKinds.length && <p className="muted" style={{ padding: 16, background: 'var(--bg)' }}>Надёжных предложений сейчас нет.</p>}
      </div>

      {sel && <div className="card"><PriceChart offerId={sel.id} currency={sel.currency} title={`${KIND_LABEL[sel.kind]}, ${sel.kind === 'магазин' ? sel.store : sel.seller}`} /></div>}

      <div className="sec-head">
        <h2>Все предложения</h2>
        <label className="check inline"><input type="checkbox" checked={all} onChange={e => setAll(e.target.checked)} /> Показать аккаунты и прочее</label>
      </div>
      <p className="muted small" style={{ marginTop: -8 }}>Нажмите на строку, чтобы увидеть историю цены этого предложения.</p>
      <OfferTable offers={offers} appid={g.appid} onSelect={setSel} selected={sel?.id} />
      {similar.length > 0 && (
        <>
          <div className="sec-head"><h2>Похожие игры</h2></div>
          <div className="tiles">{similar.map(s => <GameTile key={s.appid} g={s} />)}</div>
        </>
      )}
    </>
  )
}
