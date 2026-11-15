import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type Kind, type SearchRes } from '../api'
import { OfferTable } from '../components/OfferTable'
import { Recommend } from '../components/Recommend'
import { useApp } from '../store'
import { DEFAULT_KINDS, KIND_HINT, KIND_LABEL, regionFit } from '../util'

const ALL_KINDS: Kind[] = ['ключ', 'гифт', 'магазин', 'аккаунт', 'пополнение', 'другое']

export default function Search() {
  const [params] = useSearchParams()
  const q = params.get('q') || ''
  const { profile } = useApp()
  const [res, setRes] = useState<SearchRes | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [took, setTook] = useState(0)

  const [kinds, setKinds] = useState<Kind[]>(profile.kinds.length ? profile.kinds : DEFAULT_KINDS)
  const [platforms, setPlatforms] = useState<string[]>([])
  const [stores, setStores] = useState<'all' | 'plati' | 'official'>('all')
  const [maxPrice, setMaxPrice] = useState('')
  const [trusted, setTrusted] = useState(true)
  const [regionOk, setRegionOk] = useState(false)

  useEffect(() => {
    if (q.length < 2) return
    let alive = true
    const t0 = performance.now()
    setLoading(true)
    setErr(null)
    setPlatforms([])
    api.search(q).then(r => { if (alive) { setRes(r); setTook((performance.now() - t0) / 1000) } })
      .catch(e => alive && setErr(e.message))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [q])

  const offers = useMemo(() => (res?.offers || []).filter(o =>
    kinds.includes(o.kind) &&
    (!platforms.length || platforms.includes(o.platform)) &&
    (stores === 'all' || (stores === 'plati') === (o.store === 'plati.market')) &&
    (!maxPrice || o.price <= Number(maxPrice)) &&
    (!trusted || o.trusted) &&
    (!regionOk || regionFit(o, profile.region) !== 'no')), [res, kinds, platforms, stores, maxPrice, trusted, regionOk, profile.region])

  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter(x => x !== v) : [...list, v])

  if (q.length < 2) return <div className="empty"><h2>Введите название игры в поиске сверху</h2></div>

  return (
    <div className="layout">
      <aside className="filters card">
        <h3>Тип товара</h3>
        {ALL_KINDS.map(k => (
          <label key={k} className="check" title={KIND_HINT[k]}>
            <input type="checkbox" checked={kinds.includes(k)} onChange={() => setKinds(toggle(kinds, k))} />
            {KIND_LABEL[k]} <span className="muted">{res?.facets.kinds[k] ?? 0}</span>
          </label>
        ))}
        {kinds.includes('аккаунт') && <p className="warn small">Аккаунт — общий доступ, игра не станет вашей.</p>}
        <h3>Платформа</h3>
        {Object.entries(res?.facets.platforms || {}).sort((a, b) => b[1] - a[1]).map(([p, n]) => (
          <label key={p} className="check">
            <input type="checkbox" checked={platforms.includes(p)} onChange={() => setPlatforms(toggle(platforms, p))} />
            {p === '?' ? 'Не указана' : p} <span className="muted">{n}</span>
          </label>
        ))}
        <h3>Магазин</h3>
        <select value={stores} onChange={e => setStores(e.target.value as typeof stores)} aria-label="Магазин">
          <option value="all">Все площадки</option>
          <option value="plati">Только Plati.market</option>
          <option value="official">Только официальные</option>
        </select>
        <label>Цена до, ₽<input type="number" min={0} value={maxPrice} onChange={e => setMaxPrice(e.target.value)} placeholder={profile.budget ? String(profile.budget) : ''} /></label>
        <label className="check"><input type="checkbox" checked={trusted} onChange={e => setTrusted(e.target.checked)} /> Только надёжные продавцы</label>
        <label className="check"><input type="checkbox" checked={regionOk} onChange={e => setRegionOk(e.target.checked)} /> Скрыть не подходящие по региону ({profile.region})</label>
      </aside>

      <section>
        {loading && <div className="loading"><span className="spinner" /> Ищем «{q}» в магазинах… обычно 2–8 секунд</div>}
        {err && <div className="error">{err} <button className="btn small" onClick={() => location.reload()}>Повторить</button></div>}
        {res && !loading && (
          <>
            {res.warnings.map(w => <div key={w} className="notice">{w}</div>)}
            {res.game ? (
              <div className="game-head card">
                {res.game.image && <img src={res.game.image} alt="" />}
                <div>
                  <h1>{res.game.name}</h1>
                  <p className="muted">{res.game.genres.join(', ')}{res.game.metacritic ? ` · Metacritic ${res.game.metacritic}` : ''}
                    {res.game.steam_review_pct != null ? ` · ${res.game.steam_review_pct}% положительных отзывов Steam` : ''}</p>
                  <Link to={`/game/${res.game.appid}`} className="btn small">Карточка игры и график цены →</Link>
                </div>
              </div>
            ) : <h1>Результаты по «{q}»</h1>}
            <p className="muted small">
              Найдено {res.total_found} предложений, к товару относятся {res.matched}, под фильтры — {offers.length}. Поиск занял {took.toFixed(1)} с.
            </p>
            <Recommend offers={res.offers} where="search" query={q} />
            <OfferTable offers={offers} appid={res.game?.appid} />
          </>
        )}
      </section>
    </div>
  )
}
