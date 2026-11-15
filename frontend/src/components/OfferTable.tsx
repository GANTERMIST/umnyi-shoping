import { useMemo, useState } from 'react'
import type { Offer } from '../api'
import { useApp } from '../store'
import { Heart } from './Icons'
import { byPrice, delivery, guarantee, KIND_HINT, KIND_LABEL, money, price, regionFit, regionText, trustLabel } from '../util'

type Col = 'price' | 'trust' | 'sold' | 'store' | 'kind'

const COLS: { key: Col; label: string }[] = [
  { key: 'store', label: 'Магазин / продавец' },
  { key: 'kind', label: 'Тип' },
  { key: 'trust', label: 'Надёжность' },
  { key: 'price', label: 'Цена' },
]

function cmp(a: Offer, b: Offer, col: Col): number {
  switch (col) {
    case 'price': return byPrice(a, b)
    case 'trust': return Number(b.trusted) - Number(a.trusted) || b.trust_score - a.trust_score
    case 'sold': return b.sold - a.sold
    case 'store': return a.store.localeCompare(b.store) || a.seller.localeCompare(b.seller)
    case 'kind': return a.kind.localeCompare(b.kind)
  }
}

export function OfferTable({ offers, appid, onSelect, selected }: {
  offers: Offer[]
  appid?: number | null
  onSelect?: (o: Offer) => void
  selected?: string | null
}) {
  const { isFav, toggleFav, inCompare, toggleCompare, profile } = useApp()
  const [sort, setSort] = useState<{ col: Col; dir: 1 | -1 }>({ col: 'price', dir: 1 })
  const [note, setNote] = useState<string | null>(null)
  const rows = useMemo(() => offers.slice().sort((a, b) => cmp(a, b, sort.col) * sort.dir), [offers, sort])

  const head = (c: { key: Col; label: string }) => (
    <th key={c.key} className={c.key === 'price' ? 'num' : ''}>
      <button className="th-sort" onClick={() => setSort(s => ({ col: c.key, dir: s.col === c.key ? (-s.dir as 1 | -1) : 1 }))}
        aria-label={`Сортировать по колонке «${c.label}»`}>
        {c.label}{sort.col === c.key ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
      </button>
    </th>
  )

  if (!offers.length) return <p className="muted">Под выбранные фильтры предложений нет — ослабьте условия слева.</p>

  return (
    <>
      {note && <div className="toast" onAnimationEnd={() => setNote(null)}>{note}</div>}
      <div className="table-wrap">
        <table className="offers">
          <thead>
            <tr>
              <th>Предложение</th>
              {COLS.map(head)}
              <th aria-label="Действия" />
            </tr>
          </thead>
          <tbody>
            {rows.map(o => {
              const fit = regionFit(o, profile.region)
              return (
                <tr key={o.id} className={selected === o.id ? 'sel' : ''} onClick={() => onSelect?.(o)}>
                  <td className="title-cell">
                    <a href={o.url} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}>{o.title}</a>
                    <div className="sub">
                      <span className="pill">{o.platform === '?' ? 'Платформа ?' : o.platform}</span>
                      <span className={`region ${fit}`} title="Регион активации из описания продавца">{regionText(o, profile.region)}</span>
                      <span>{delivery(o)}</span>
                    </div>
                    {o.note && <div className="sub muted small">{o.note}</div>}
                    <div className="sub muted small" title="Условия возврата и гарантии">{guarantee(o)}</div>
                  </td>
                  <td>
                    <div>{o.kind === 'магазин' ? o.store : o.seller}</div>
                    <div className="muted small">{o.kind === 'магазин' ? 'официальный' : o.store}</div>
                  </td>
                  <td><span className={`kind k-${o.kind}`} title={KIND_HINT[o.kind]}>{KIND_LABEL[o.kind]}</span></td>
                  <td>
                    <span className={o.trusted ? 'ok' : 'warn'}>{trustLabel(o)}</span>
                    {o.kind !== 'магазин' && <div className="muted small">+{o.reviews_pos} / −{o.reviews_neg}{o.returns ? `, возвратов ${o.returns}` : ''}</div>}
                    {o.kind !== 'магазин' && <div className="muted small">продано {o.sold.toLocaleString('ru-RU')}</div>}
                  </td>
                  <td className="num price">
                    {price(o)}
                    {o.old_price && <div className="old">{money(o.old_price, o.currency)}</div>}
                  </td>
                  <td className="actions" onClick={e => e.stopPropagation()}>
                    <div>
                      <label className="cmp" title="Добавить к сравнению">
                        <input type="checkbox" checked={inCompare(o.id)} onChange={() => setNote(toggleCompare(o))} aria-label="Сравнить" />
                      </label>
                      <button className={`icon ${isFav(o.id) ? 'on' : ''}`} onClick={() => toggleFav(o, appid)}
                        title={isFav(o.id) ? 'Убрать из избранного' : 'Следить за ценой'} aria-label="Избранное"><Heart /></button>
                    </div>
                    <div><a className="btn small" href={o.url} target="_blank" rel="noopener noreferrer">Купить ↗</a></div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}
