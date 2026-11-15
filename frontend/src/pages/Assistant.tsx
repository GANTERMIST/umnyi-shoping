import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type Nlu, type Offer } from '../api'
import { useApp } from '../store'
import { delivery, KIND_LABEL, rub } from '../util'
import { Feedback } from '../components/Feedback'

interface Msg { role: 'user' | 'assistant'; text: string; offers?: Offer[]; engine?: string; took?: number; nlu?: Nlu | null }

const INTENT_LABEL: Record<Nlu['intent'], string> = {
  buy: 'купить', recommend: 'подобрать игру', review: 'отзывы', compare: 'сравнить цены', faq: 'вопрос о сервисе',
  greet: 'приветствие', other: 'не про игры',
}
const ENGINE_LABEL: Record<string, string> = { model: 'своя модель ShopNLU', rules: 'режим правил', claude: 'Claude API' }

/** Как модель поняла запрос: намерение и найденные «слоты». */
function Understood({ n }: { n: Nlu }) {
  const chips = [
    `${INTENT_LABEL[n.intent]} · ${Math.round(n.confidence * 100)}%`,
    n.game && `игра: ${n.game}${n.query && n.query.toLowerCase() !== n.game.toLowerCase() ? ` → ${n.query}` : ''}`,
    n.kind && `тип: ${KIND_LABEL[n.kind]}`,
    n.platform && `платформа: ${n.platform}`,
    n.max_price && `до ${rub(n.max_price)}`,
    n.genre_text && `жанр: ${n.genre_text}`,
  ].filter(Boolean) as string[]
  return (
    <div className="understood" title="Так запрос разобрала своя нейросеть ShopNLU">
      <span className="muted tiny">Понял:</span>
      {chips.map(c => <span key={c} className="nlu-chip">{c}</span>)}
    </div>
  )
}

const EXAMPLES = ['Где дешевле ключ Cyberpunk 2077 для Steam?', 'Посоветуй рпг до 1000', 'Стоит ли брать Hades?',
  'Ведьмак 3 в стиме или у продавцов?', 'Хочу робуксы до 1к', 'Чем ключ отличается от гифта?']

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
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, busy])
  useEffect(() => { try { localStorage.setItem('us.chat', JSON.stringify(msgs.slice(-40))) } catch { /* */ } }, [msgs])

  return (
    <div className="chat-page">
      <div className="sec-head">
        <h1>Помощник</h1>
        {msgs.length > 0 && <button className="btn ghost small" onClick={() => setMsgs([])}>Новый диалог</button>}
      </div>
      <p className="muted small">
        Спросите своими словами — помощник найдёт предложения и объяснит выбор.
        {(profile.budget || profile.platform) && <> Учитываю профиль: {profile.budget ? `бюджет ${rub(profile.budget)}` : ''}{profile.platform ? ` · ${profile.platform}` : ''} (<Link to="/profile">изменить</Link>).</>}
      </p>
      <div className="chat card">
        {!msgs.length && (
          <div className="chips">{EXAMPLES.map(e => <button key={e} className="chip" onClick={() => send(e)}>{e}</button>)}</div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.nlu && <Understood n={m.nlu} />}
            <div className="bubble">{m.text}</div>
            {m.offers && m.offers.length > 0 && (
              <div className="msg-offers">
                {m.offers.map(o => (
                  <div key={o.id} className="mini card">
                    <div className="mini-title">{o.title}</div>
                    <div className="muted small">{KIND_LABEL[o.kind]} · {o.platform} · {o.kind === 'магазин' ? o.store : o.seller}</div>
                    <div className="muted small">{delivery(o)}</div>
                    <div className="mini-foot">
                      <b>{rub(o.price)}</b>
                      <button className={`icon ${isFav(o.id) ? 'on' : ''}`} onClick={() => toggleFav(o)} aria-label="Избранное">♥</button>
                      <a className="btn small" href={o.url} target="_blank" rel="noopener noreferrer">Купить →</a>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {m.offers && m.offers.length > 0 && <Feedback where="assistant" offerId={m.offers[0].id} query={msgs[i - 1]?.text} />}
            {m.engine && <div className="muted tiny">{ENGINE_LABEL[m.engine] ?? m.engine} · {m.took?.toFixed(1)} с</div>}
          </div>
        ))}
        {busy && <div className="msg assistant"><div className="bubble"><span className="spinner" /> Ищу предложения…</div></div>}
        <div ref={end} />
      </div>
      <form className="chat-form" onSubmit={e => { e.preventDefault(); send(text) }}>
        <input value={text} onChange={e => setText(e.target.value)} placeholder="Например: ключ Elden Ring в Steam до 2000" aria-label="Сообщение" />
        <button className="btn primary" disabled={busy || !text.trim()}>Отправить</button>
      </form>
    </div>
  )
}
