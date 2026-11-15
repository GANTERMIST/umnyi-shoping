import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type TelegramUser } from '../api'
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

  // Вход через Telegram: официальный виджет telegram.org, подпись проверяет сервер
  const tgBox = useRef<HTMLDivElement>(null)
  const [tgBot, setTgBot] = useState<string | null | undefined>(undefined)
  useEffect(() => { api.telegramConfig().then(c => setTgBot(c.bot)).catch(() => setTgBot(null)) }, [])
  useEffect(() => {
    if (!tgBot || !tgBox.current) return
    const w = window as unknown as { onTelegramAuth?: (u: TelegramUser) => void }
    w.onTelegramAuth = async (u: TelegramUser) => {
      setErr(null); setBusy(true)
      try { signedIn(await api.telegram(u)); nav('/profile') } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
    }
    const s = document.createElement('script')
    s.src = 'https://telegram.org/js/telegram-widget.js?22'
    s.async = true
    s.dataset.telegramLogin = tgBot
    s.dataset.size = 'large'
    s.dataset.radius = '0'
    s.dataset.requestAccess = 'write'
    s.dataset.onauth = 'onTelegramAuth(user)'
    tgBox.current.replaceChildren(s)
    return () => { delete w.onTelegramAuth }
  }, [tgBot, nav, signedIn])

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
        <div ref={tgBox} />
        {tgBot === null && <p className="muted small">Вход через Telegram появится, когда к сайту подключат бота.</p>}
        {tgBot && <p className="muted small">{mode === 'register' ? 'Регистрация' : 'Вход'} в один клик через Telegram — без пароля. Или по почте:</p>}
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
