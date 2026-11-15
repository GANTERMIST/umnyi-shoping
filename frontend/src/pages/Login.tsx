import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useApp } from '../store'

export default function Login() {
  const { signedIn } = useApp()
  const nav = useNavigate()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Вход через Telegram-бота: кнопка открывает бота с одноразовым кодом, пользователь жмёт «Старт»,
  // вкладка опрашивает сервер и входит сама. Новый пользователь регистрируется при первом входе.
  const [tgBot, setTgBot] = useState<string | null | undefined>(undefined)
  const [tgCode, setTgCode] = useState<string | null>(null)
  const expired = new URLSearchParams(location.search).get('tg') === 'expired'
  useEffect(() => { api.telegramConfig().then(c => setTgBot(c.bot)).catch(() => setTgBot(null)) }, [])
  useEffect(() => {
    if (!tgCode) return
    let stop = false
    const started = Date.now()
    const tick = async () => {
      if (stop) return
      if (Date.now() - started > 10 * 60e3) { setTgCode(null); setErr('Время ожидания вышло — нажмите кнопку ещё раз'); return }
      try {
        const r = await api.telegramPoll(tgCode)
        if ('user' in r) { signedIn(r); nav('/profile'); return }
      } catch { /* сеть моргнула — пробуем дальше */ }
      setTimeout(tick, 2000)
    }
    tick()
    return () => { stop = true }
  }, [tgCode, nav, signedIn])

  const tgStart = () => {
    const b = new Uint8Array(16)
    crypto.getRandomValues(b)
    const code = Array.from(b, x => x.toString(16).padStart(2, '0')).join('')
    setErr(null)
    setTgCode(code)
    window.open(`https://t.me/${tgBot}?start=${code}`, '_blank', 'noopener')
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr(null)
    if (password.length < 8) return setErr('Пароль — не короче 8 символов')
    setBusy(true)
    try {
      const me = mode === 'login' ? await api.login(email, password) : await api.register(email, password, name || undefined)
      signedIn(me)
      nav('/profile')
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth card">
      <div className="tabs">
        <button className={mode === 'login' ? 'on' : ''} onClick={() => setMode('login')}>Вход</button>
        <button className={mode === 'register' ? 'on' : ''} onClick={() => setMode('register')}>Регистрация</button>
      </div>
      <div className="tg-login">
        {expired && <p className="error">Ссылка из бота устарела — нажмите кнопку ещё раз.</p>}
        {tgBot && !tgCode && (
          <button type="button" className="btn tg-btn" onClick={tgStart}>
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M21.9 4.3 18.6 20c-.2 1.1-.9 1.4-1.8.9l-5-3.7-2.4 2.3c-.3.3-.5.5-1 .5l.4-5.1 9.2-8.3c.4-.4-.1-.6-.6-.2L6 13.6l-4.9-1.5c-1.1-.3-1.1-1.1.2-1.6L20.5 3c.9-.3 1.7.2 1.4 1.3Z"/></svg>
            {mode === 'register' ? 'Зарегистрироваться через Telegram' : 'Войти через Telegram'}
          </button>
        )}
        {tgCode && (
          <div className="tg-wait">
            <p><span className="spinner" /> Откройте бота @{tgBot} и нажмите <b>«Старт»</b> — вход произойдёт сам.</p>
            <p className="small">
              <a href={`https://t.me/${tgBot}?start=${tgCode}`} target="_blank" rel="noopener noreferrer">Открыть бота ещё раз</a>
              {' · '}<button type="button" className="link" onClick={() => setTgCode(null)}>Отмена</button>
            </p>
          </div>
        )}
        {tgBot === null && <p className="muted small">Вход через Telegram появится, когда к сайту подключат бота.</p>}
        {tgBot && <p className="muted small">Без пароля: аккаунт создаётся при первом входе. Или по почте:</p>}
      </div>
      <form onSubmit={submit}>
        {mode === 'register' && <label>Имя<input value={name} onChange={e => setName(e.target.value)} autoComplete="name" /></label>}
        <label>Почта<input type="email" required value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" /></label>
        <label>Пароль<input type="password" required minLength={8} value={password} onChange={e => setPassword(e.target.value)}
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'} /></label>
        {err && <p className="error">{err}</p>}
        <button className="btn primary" disabled={busy}>{busy ? '…' : mode === 'login' ? 'Войти' : 'Создать аккаунт'}</button>
      </form>
      <p className="muted small">Пароль хранится только в виде хэша (PBKDF2). После 5 неверных попыток вход блокируется на 15 минут.
        Избранное и профиль с этого устройства перенесутся в аккаунт.</p>
    </div>
  )
}
