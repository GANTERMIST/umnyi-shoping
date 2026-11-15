import { useState } from 'react'
import { api } from '../api'

/** «Помогла ли рекомендация?» — ключевой критерий брифа (≥ 60% «да»). Голос запоминается в браузере. */
export function Feedback({ where, offerId, query }: { where: 'search' | 'game' | 'assistant' | 'compare'; offerId?: string; query?: string }) {
  const key = `us.fb.${where}.${offerId || query || ''}`
  const [voted, setVoted] = useState<string | null>(() => {
    try { return localStorage.getItem(key) } catch { return null }
  })
  const vote = (helpful: boolean) => {
    api.feedback(helpful, where, offerId, query).catch(() => {})
    const v = helpful ? 'yes' : 'no'
    setVoted(v)
    try { localStorage.setItem(key, v) } catch { /* приватный режим */ }
  }
  if (voted) return <div className="feedback muted small">{voted === 'yes' ? 'Спасибо, ответ записан.' : 'Спасибо, учтём при подборе.'}</div>
  return (
    <div className="feedback small">
      <span className="muted">Рекомендация помогла выбрать?</span>
      <button className="btn small ghost" onClick={() => vote(true)}>Да</button>
      <button className="btn small ghost" onClick={() => vote(false)}>Нет</button>
    </div>
  )
}
