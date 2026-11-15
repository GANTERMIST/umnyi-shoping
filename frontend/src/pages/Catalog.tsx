import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, type CatalogItem } from '../api'
import { GameTile, Skeletons } from '../components/GameTile'

type Sort = 'popular' | 'price' | 'savings' | 'rating'

export default function Catalog() {
  const [params, setParams] = useSearchParams()
  const [items, setItems] = useState<CatalogItem[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [genre, setGenre] = useState('')
  const [maxPrice, setMaxPrice] = useState('')
  const sort = (params.get('sort') as Sort) || 'popular'

  useEffect(() => { api.catalog(500).then(setItems).catch(e => setErr(e.message)) }, [])

  const genres = useMemo(() => [...new Set((items || []).flatMap(i => i.genres))].sort(), [items])
  const list = useMemo(() => {
    let r = (items || []).filter(i =>
      (!text || i.name.toLowerCase().includes(text.toLowerCase())) &&
      (!genre || i.genres.includes(genre)) &&
      (!maxPrice || (i.best_price != null && i.best_price <= Number(maxPrice))))
    const by: Record<Sort, (a: CatalogItem, b: CatalogItem) => number> = {
      popular: (a, b) => b.offers - a.offers,
      price: (a, b) => (a.best_price ?? 1e9) - (b.best_price ?? 1e9),
      savings: (a, b) => (b.savings_pct ?? 0) - (a.savings_pct ?? 0),
      rating: (a, b) => (b.steam_review_pct ?? 0) - (a.steam_review_pct ?? 0),
    }
    r = r.slice().sort(by[sort])
    return r
  }, [items, text, genre, maxPrice, sort])

  return (
    <div className="layout">
      <aside className="filters card">
        <h3>Фильтры</h3>
        <label>Название<input value={text} onChange={e => setText(e.target.value)} placeholder="например, hades" /></label>
        <label>Жанр
          <select value={genre} onChange={e => setGenre(e.target.value)}>
            <option value="">Любой</option>
            {genres.map(g => <option key={g}>{g}</option>)}
          </select>
        </label>
        <label>Цена до, ₽<input type="number" min={0} value={maxPrice} onChange={e => setMaxPrice(e.target.value)} /></label>
        <button className="btn ghost" onClick={() => { setText(''); setGenre(''); setMaxPrice('') }}>Сбросить</button>
      </aside>
      <section>
        <div className="sec-head">
          <h1>Каталог игр</h1>
          <label className="inline">Сортировка
            <select value={sort} onChange={e => setParams({ sort: e.target.value })}>
              <option value="popular">Больше предложений</option>
              <option value="price">Дешевле</option>
              <option value="savings">Выгоднее официальной цены</option>
              <option value="rating">Отзывы Steam</option>
            </select>
          </label>
        </div>
        {err && <p className="error">{err}</p>}
        {!items ? <Skeletons n={8} /> : list.length ? (
          <>
            <p className="muted small">{list.length} игр в базе. Цены обновляет загрузчик; свежие — по клику на игру.</p>
            <div className="tiles">{list.map(g => <GameTile key={g.appid} g={g} />)}</div>
          </>
        ) : <p className="muted">Ничего не найдено. Попробуйте поиск сверху — сервис найдёт игру в реальном времени.</p>}
      </section>
    </div>
  )
}
