import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type CatalogItem } from '../api'
import { GameTile, Skeletons } from '../components/GameTile'
import { useApp } from '../store'
import { money, price } from '../util'

const CHIPS = [
  'Ключ Elden Ring для Steam до 2000',
  'Cyberpunk 2077 подешевле',
  'Baldur’s Gate 3 гифт',
  'Робуксы до 1000',
]

export default function Home() {
  const nav = useNavigate()
  const { favorites, prices, compare, viewed } = useApp()
  const [text, setText] = useState('')
  const [deals, setDeals] = useState<CatalogItem[] | null>(null)
  const [popular, setPopular] = useState<CatalogItem[] | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.deals(8).then(setDeals).catch(e => setErr(e.message))
    api.catalog(8).then(setPopular).catch(e => setErr(e.message))
  }, [])

  const ask = (t: string) => {
    if (t.trim()) nav(`/assistant?q=${encodeURIComponent(t.trim())}`)
  }

  return (
    <>
      <section className="hero">
        <h1>Опишите задачу. Сервис найдёт товар и сравнит цены всех магазинов.</h1>
        <form className="hero-form" onSubmit={e => { e.preventDefault(); ask(text) }}>
          <input value={text} onChange={e => setText(e.target.value)} autoFocus
            placeholder="Например: ключ Hades для Steam до 800 рублей" aria-label="Что ищете" />
          <button className="btn primary" type="submit">Подобрать</button>
        </form>
        <div className="chips">
          {CHIPS.map(c => <button key={c} className="chip" onClick={() => ask(c)}>{c}</button>)}
        </div>
        <p className="muted small">Ищем у продавцов Plati.market и в официальных магазинах (Steam, GOG, Humble, Fanatical…), проверяем надёжность продавца и регион активации.</p>
      </section>

      {err && <p className="error">{err}</p>}

      <section>
        <div className="sec-head"><h2>Выгодно сегодня</h2><Link to="/catalog?sort=savings">Все скидки</Link></div>
        {!deals ? <Skeletons /> : deals.length ? (
          <div className="tiles">{deals.map(g => <GameTile key={g.appid} g={g} />)}</div>
        ) : <p className="muted">Скидок пока нет. Загрузите цены: <code>python -m app.loader</code> или поищите игру.</p>}
      </section>

      <div className="two-col">
        <section className="card">
          <div className="sec-head"><h2>Отслеживаю</h2><Link to="/favorites">Всё избранное</Link></div>
          {favorites.length ? (
            <ul className="watch">
              {favorites.slice(0, 5).map(f => {
                const now = prices[f.offer_id]
                const diff = now != null ? now - f.price : 0
                return (
                  <li key={f.offer_id}>
                    <span className="ellipsis">{f.title}</span>
                    <b>{money(now ?? f.price, f.currency)}</b>
                    {diff !== 0 && <span className={diff < 0 ? 'down' : 'up'}>{diff < 0 ? '▼' : '▲'} {money(Math.abs(diff), f.currency)}</span>}
                  </li>
                )
              })}
            </ul>
          ) : <p className="muted">Нажмите на сердце у предложения, и здесь появится его цена.</p>}
        </section>
        <section className="card">
          <div className="sec-head"><h2>Сравнение</h2><Link to="/compare">Открыть</Link></div>
          {compare.length ? (
            <ul className="watch">{compare.map(o => <li key={o.id}><span className="ellipsis">{o.title}</span><b>{price(o)}</b></li>)}</ul>
          ) : <p className="muted">Отметьте «Сравнить» у 2–4 предложений, чтобы увидеть их рядом.</p>}
        </section>
      </div>

      {viewed.length > 0 && (
        <section>
          <div className="sec-head"><h2>Вы смотрели</h2></div>
          <div className="viewed">
            {viewed.slice(0, 8).map(v => (
              <Link key={v.appid} to={`/game/${v.appid}`} className="viewed-item">
                {v.image ? <img src={v.image} alt="" loading="lazy" /> : <div className="noimg" />}
                <span className="ellipsis small">{v.name}</span>
              </Link>
            ))}
          </div>
        </section>
      )}

      <section>
        <div className="sec-head"><h2>Популярное сейчас</h2><Link to="/catalog">Весь каталог</Link></div>
        {!popular ? <Skeletons /> : popular.length ? (
          <div className="tiles">{popular.map(g => <GameTile key={g.appid} g={g} />)}</div>
        ) : <p className="muted">Каталог пуст — запустите загрузчик цен.</p>}
      </section>
    </>
  )
}
