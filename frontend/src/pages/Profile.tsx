import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { Kind, Profile } from '../api'
import { useApp } from '../store'
import { KIND_HINT, KIND_LABEL, REGION_LABEL, USER_REGIONS } from '../util'

const KINDS: Kind[] = ['ключ', 'гифт', 'магазин', 'аккаунт', 'пополнение']
const PLATFORMS = ['Steam', 'Xbox', 'PlayStation', 'Nintendo', 'GOG', 'Epic']

export default function ProfilePage() {
  const { user, profile, setProfile, signOut } = useApp()
  const nav = useNavigate()
  const [p, setP] = useState<Profile>(profile)
  const [saved, setSaved] = useState(false)

  const save = (e: React.FormEvent) => {
    e.preventDefault()
    setProfile(p)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="auth card wide">
      <h1>Профиль покупателя</h1>
      {user
        ? <p className="muted">Вы вошли как <b>{user.email.startsWith('tg:') ? `${user.name ?? 'пользователь'} (Telegram)` : user.email}</b>. Профиль и избранное сохраняются в аккаунте.</p>
        : <p className="muted">Профиль хранится в этом браузере. <Link to="/login">Войдите</Link>, чтобы он был на всех устройствах.</p>}
      <form onSubmit={save}>
        <label>Бюджет на игру, ₽
          <input type="number" min={0} value={p.budget ?? ''} onChange={e => setP({ ...p, budget: e.target.value ? Number(e.target.value) : null })} placeholder="например, 2000" />
        </label>
        <label>Платформа
          <select value={p.platform ?? ''} onChange={e => setP({ ...p, platform: e.target.value || null })}>
            <option value="">Любая</option>
            {PLATFORMS.map(x => <option key={x}>{x}</option>)}
          </select>
        </label>
        <label>Где активировать (регион аккаунта)
          <select value={p.region} onChange={e => setP({ ...p, region: e.target.value })}>
            {USER_REGIONS.map(r => <option key={r} value={r}>{REGION_LABEL[r]}</option>)}
          </select>
        </label>
        <fieldset>
          <legend>Какие товары подходят</legend>
          {KINDS.map(k => (
            <label key={k} className="check" title={KIND_HINT[k]}>
              <input type="checkbox" checked={p.kinds.includes(k)}
                onChange={() => setP({ ...p, kinds: p.kinds.includes(k) ? p.kinds.filter(x => x !== k) : [...p.kinds, k] })} />
              {KIND_LABEL[k]} <span className="muted small">— {KIND_HINT[k]}</span>
            </label>
          ))}
          <p className="muted small">Ничего не выбрано — ключи, гифты и официальные магазины.</p>
        </fieldset>
        <div className="row">
          <button className="btn primary">Сохранить</button>
          {saved && <span className="ok">Сохранено</span>}
          {user && <button type="button" className="btn ghost" onClick={async () => { await signOut(); nav('/') }}>Выйти</button>}
        </div>
      </form>
    </div>
  )
}
