import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, type Kind, type Nlu, type Offer, type Profile } from '../api'
import { Feedback } from '../components/Feedback'
import { Heart } from '../components/Icons'
import { useApp } from '../store'
import { delivery, KIND_LABEL, price, rub } from '../util'

interface Msg { role: 'user' | 'assistant'; text: string; offers?: Offer[]; engine?: string; took?: number; nlu?: Nlu | null }

const INTENT_LABEL: Record<Nlu['intent'], string> = {
  buy: 'купить', recommend: 'подобрать игру', review: 'отзывы', compare: 'сравнить цены', faq: 'вопрос о сервисе',
  greet: 'приветствие', other: 'не про игры',
}
const ENGINE_LABEL: Record<string, string> = { model: 'своя модель ShopNLU', rules: 'режим правил', claude: 'Claude API' }
const PLATFORMS = ['Steam', 'Xbox', 'PlayStation', 'Nintendo', 'GOG', 'Epic']
const KINDS: Kind[] = ['ключ', 'гифт', 'магазин', 'аккаунт', 'пополнение']
const EXAMPLES = ['Где дешевле ключ Cyberpunk 2077 для Steam?', 'Посоветуй рпг до 1000', 'Стоит ли брать Hades?',
  'Ведьмак 3 в стиме или у продавцов?', 'Хочу робуксы до 1к', 'Чем ключ отличается от гифта?']

/** Как модель поняла запрос: намерение и найденные условия. */
function Understood({ n }: { n: Nlu }) {
  const chips = [
    `${INTENT_LABEL[n.intent]} ${Math.round(n.confidence * 100)}%`,
    n.game && `${n.game}${n.query && n.query.toLowerCase() !== n.game.toLowerCase() ? ` = ${n.query}` : ''}`,
    n.kind && KIND_LABEL[n.kind].toLowerCase(),
    n.platform,
    n.max_price && `до ${rub(n.max_price)}`,
    n.genre_text && `жанр ${n.genre_text}`,
  ].filter(Boolean) as string[]
  return (
    <div className="understood" title="Так запрос разобрала своя нейросеть ShopNLU">
      <span>Понял</span>
      {chips.map(c => <span key={c} className="nlu-chip">{c}</span>)}
    </div>
  )
}

/** Подпись карточки: в чём это предложение лучше остальных. */
function cardLabel(o: Offer, all: Offer[]): string {
  const same = all.filter(x => x.currency === o.currency)
  if (o.price === Math.min(...same.map(x => x.price))) return o.currency === 'USD' ? 'Официально' : 'Мин. цена'
  if (o.trust_score === Math.max(...all.map(x => x.trust_score))) return 'Надёжнее'
  return 'Вариант'
}

/** Условия подбора (Ф21): тот же профиль, правится прямо рядом с диалогом. */
function Conditions() {
  const { profile, setProfile } = useApp()
  const [p, setP] = useState<Profile>(profile)
  const [saved, setSaved] = useState(false)
  useEffect(() => setP(profile), [profile])
  return (
    <aside className="conditions">
      <h2>Условия подбора</h2>
      <p className="muted small">Помощник учитывает их, если в вопросе не сказано иначе.</p>
      <label>Бюджет, ₽
        <input type="number" min={0} value={p.budget ?? ''} placeholder="без ограничения"
          onChange={e => setP({ ...p, budget: e.target.value ? Number(e.target.value) : null })} />
      </label>
      <label>Платформа
        <select value={p.platform ?? ''} onChange={e => setP({ ...p, platform: e.target.value || null })}>
          <option value="">Любая</option>
          {PLATFORMS.map(x => <option key={x}>{x}</option>)}
        </select>
      </label>
      <h3>Что подходит</h3>
      {KINDS.map(k => (
        <label key={k} className="check">
          <input type="checkbox" checked={p.kinds.includes(k)}
            onChange={() => setP({ ...p, kinds: p.kinds.includes(k) ? p.kinds.filter(x => x !== k) : [...p.kinds, k] })} />
          {KIND_LABEL[k]}
        </label>
      ))}
      <button className="btn primary" onClick={() => { setProfile(p); setSaved(true); setTimeout(() => setSaved(false), 1800) }}>
        {saved ? 'Сохранено' : 'Применить'}
      </button>
    </aside>
  )
}

export default function Assistant() {
  const [params, setParams] = useSearchParams()
  const { profile, toggleFav, isFav } = useApp()
  // история диалога сохраняется в браузере (Ф22): можно уйти со страницы и продолжить
  const [msgs, setMsgs] = useState<Msg[]>(() => {
    try { return JSON.parse(localStorage.getItem('us.chat') || '[]') } catch { return [] }
  })
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const end = useRef<HTMLDivElement>(null)
  const started = useRef(false)

  const send = async (t: string) => {
    const message = t.trim()
    if (!message || busy) return
    const history = msgs.map(m => ({ role: m.role, text: m.text })).slice(-10)
    setMsgs(m => [...m, { role: 'user', text: message }])
    setText('')
    setBusy(true)
    const t0 = performance.now()
    try {
      const r = await api.assistant(message, history, profile)
      setMsgs(m => [...m, { role: 'assistant', text: r.answer, offers: r.offers, engine: r.engine, nlu: r.nlu,
        took: (performance.now() - t0) / 1000 }])
    } catch (e) {
      setMsgs(m => [...m, { role: 'assistant', text: `Не получилось: ${(e as Error).message}` }])
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    const q = params.get('q')
    if (q && !started.current) {
      started.current = true
      setParams({}, { replace: true })
      send(q)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }) }, [msgs, busy])
  useEffect(() => { try { localStorage.setItem('us.chat', JSON.stringify(msgs.slice(-40))) } catch { /* */ } }, [msgs])

  return (
    <div className="chat-page">
      <div className="chat-main">
        <div className="chat-top">
          <h1>Помощник</h1>
          {msgs.length > 0 && <button className="btn ghost small" onClick={() => setMsgs([])}>Новый диалог</button>}
        </div>
        <div className="chat">
          {!msgs.length && (
            <div>
              <p className="muted">Опишите, что ищете, своими словами. Помощник найдёт предложения у продавцов и в официальных
                магазинах и объяснит, почему советует именно их.</p>
              <div className="chips">{EXAMPLES.map(e => <button key={e} className="chip" onClick={() => send(e)}>{e}</button>)}</div>
            </div>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={`msg ${m.role}`} data-who={m.role === 'user' ? 'Вы' : 'Ответ'}>
              {m.nlu && <Understood n={m.nlu} />}
              <div className="bubble">{m.text}</div>
              {m.offers && m.offers.length > 0 && (
                <div className="msg-offers">
                  {m.offers.map(o => (
                    <div key={o.id} className="mini">
                      <div className="mini-label">{cardLabel(o, m.offers!)}</div>
                      <div className="mini-title">{o.title}</div>
                      <div className="muted small">{KIND_LABEL[o.kind]} / {o.platform} / {o.kind === 'магазин' ? o.store : o.seller}</div>
                      <div className="muted small">{delivery(o)}</div>
                      <div className="mini-foot">
                        <b>{price(o)}</b>
                        <button className={`icon ${isFav(o.id) ? 'on' : ''}`} onClick={() => toggleFav(o)}
                          aria-label={isFav(o.id) ? 'Убрать из избранного' : 'Следить за ценой'}><Heart /></button>
                        <a className="btn small" href={o.url} target="_blank" rel="noopener noreferrer">Купить ↗</a>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {m.offers && m.offers.length > 0 && <Feedback where="assistant" offerId={m.offers[0].id} query={msgs[i - 1]?.text} />}
              {m.engine && <div className="tiny">{ENGINE_LABEL[m.engine] ?? m.engine}, {m.took?.toFixed(1)} с</div>}
            </div>
          ))}
          {busy && <div className="msg assistant" data-who="Ответ"><div className="bubble muted"><span className="spinner" /> Ищу предложения</div></div>}
          <div ref={end} />
        </div>
        <form className="chat-form" onSubmit={e => { e.preventDefault(); send(text) }}>
          <input value={text} onChange={e => setText(e.target.value)} placeholder="Например: ключ Elden Ring в Steam до 2000" aria-label="Сообщение" />
          <button className="btn primary" disabled={busy || !text.trim()}>Отправить</button>
        </form>
      </div>
      <Conditions />
    </div>
  )
}
