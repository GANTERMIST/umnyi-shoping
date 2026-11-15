import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApp } from '../store'
import { rub } from '../util'

export default function Favorites() {
  const { favorites, prices, removeFav, refreshPrices, user, changed, reached, setTarget } = useApp()
  const [busy, setBusy] = useState(false)

  if (!favorites.length) {
    return (
      <div className="empty">
        <h2>В избранном пусто</h2>
        <p className="muted">Нажмите ♥ у предложения — сервис запомнит цену и покажет, когда она изменится.</p>
        <Link to="/catalog" className="btn">В каталог</Link>
      </div>
    )
  }
  return (
    <>
      <div className="sec-head">
        <h1>Избранное</h1>
        <button className="btn ghost" disabled={busy} onClick={async () => { setBusy(true); await refreshPrices(); setBusy(false) }}>
          {busy ? 'Проверяем…' : 'Проверить цены'}
        </button>
      </div>
      {reached > 0 && <div className="notice hot">🎯 Целевая цена достигнута у {reached} {reached === 1 ? 'товара' : 'товаров'} — пора покупать!</div>}
      {changed > 0
        ? <div className="notice hot">🔔 Цена изменилась у {changed} {changed === 1 ? 'товара' : 'товаров'} с момента добавления</div>
        : <p className="muted small">Цены обновляются загрузчиком и при каждом поиске. Изменения подсвечиваются здесь и значком в меню.</p>}
      {!user && <p className="muted small"><Link to="/login">Войдите</Link>, чтобы избранное сохранялось на всех устройствах.</p>}
      <div className="table-wrap">
        <table className="offers">
          <thead><tr><th>Товар</th><th className="num">Цена при добавлении</th><th className="num">Сейчас</th><th className="num">Изменение</th><th className="num">Целевая цена</th><th /></tr></thead>
          <tbody>
            {favorites.map(f => {
              const now = prices[f.offer_id]
              const diff = now != null ? now - f.price : 0
              const hit = !!f.target_price && now != null && now <= f.target_price
              return (
                <tr key={f.offer_id} className={hit ? 'hit' : diff ? 'changed' : ''}>
                  <td className="title-cell">
                    {f.appid ? <Link to={`/game/${f.appid}`}>{f.title}</Link> : f.title}
                    <div className="muted small">добавлено {new Date(f.added_at).toLocaleDateString('ru-RU')}</div>
                  </td>
                  <td className="num">{rub(f.price)}</td>
                  <td className="num price">{now != null ? rub(now) : <span className="muted small">нет данных</span>}</td>
                  <td className="num">
                    {diff < 0 && <span className="down">▼ {rub(-diff)} ({Math.round((-diff / f.price) * 100)}%)</span>}
                    {diff > 0 && <span className="up">▲ {rub(diff)}</span>}
                    {!diff && <span className="muted">—</span>}
                  </td>
                  <td className="num">
                    <input className="target" type="number" min={1} defaultValue={f.target_price ?? ''} placeholder="₽"
                      aria-label="Целевая цена" title="Уведомим, когда цена станет не выше"
                      onBlur={e => setTarget(f.offer_id, e.target.value ? Number(e.target.value) : null)} />
                    {hit && <div className="ok small">🎯 достигнута</div>}
                  </td>
                  <td className="actions"><button className="btn small ghost" onClick={() => removeFav(f.offer_id)}>Убрать</button></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}
