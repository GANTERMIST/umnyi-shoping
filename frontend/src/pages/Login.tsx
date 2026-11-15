import { useState } from 'react'
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
