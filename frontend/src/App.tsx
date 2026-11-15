import { useState } from 'react'
import { Link, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { useApp } from './store'
import Home from './pages/Home'
import Catalog from './pages/Catalog'
import Search from './pages/Search'
import GamePage from './pages/Game'
import Assistant from './pages/Assistant'
import Compare from './pages/Compare'
import Favorites from './pages/Favorites'
import Login from './pages/Login'
import ProfilePage from './pages/Profile'

function SearchBox() {
  const [q, setQ] = useState('')
  const nav = useNavigate()
  return (
    <form className="topsearch" role="search" onSubmit={e => {
      e.preventDefault()
      if (q.trim().length >= 2) nav(`/search?q=${encodeURIComponent(q.trim())}`)
    }}>
      <input value={q} onChange={e => setQ(e.target.value)} placeholder="Игра или товар…" aria-label="Поиск" />
    </form>
  )
}

export default function App() {
  const { user, compare, changed, reached, theme, setTheme } = useApp()
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const close = () => setOpen(false)
  return (
    <>
      <header className="topbar">
        <div className="container bar">
          <Link to="/" className="logo" onClick={close}><span className="mark" aria-hidden="true" />Умный Шопинг</Link>
          <SearchBox />
          <button className="burger" onClick={() => setOpen(!open)} aria-label="Меню" aria-expanded={open}>☰</button>
          <nav className={open ? 'open' : ''} onClick={close}>
            <NavLink to="/catalog">Каталог</NavLink>
            <NavLink to="/assistant">Помощник</NavLink>
            <NavLink to="/compare">Сравнение{compare.length > 0 && <span className="badge">{compare.length}</span>}</NavLink>
            <NavLink to="/favorites">Избранное{(changed > 0 || reached > 0) && <span className="badge hot" title={reached ? 'Достигнута целевая цена' : 'Цена изменилась'}>{reached || changed}</span>}</NavLink>
            {user ? <NavLink to="/profile">{user.name || 'Профиль'}</NavLink> : <NavLink to="/login" className="account">Войти</NavLink>}
            <button className="theme" onClick={e => { e.stopPropagation(); setTheme(theme === 'light' ? 'dark' : 'light') }}
              aria-label="Сменить тему" title="Светлая / тёмная тема">{theme === 'light' ? 'Тёмная' : 'Светлая'}</button>
          </nav>
        </div>
      </header>
      <main className="container">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/catalog" element={<Catalog />} />
          <Route path="/search" element={<Search />} />
          <Route path="/game/:appid" element={<GamePage />} />
          <Route path="/assistant" element={<Assistant />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/favorites" element={<Favorites />} />
          <Route path="/login" element={<Login />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="*" element={<div className="empty"><h2>Страница не найдена</h2><Link to="/">На главную</Link></div>} />
        </Routes>
      </main>
      {compare.length > 0 && pathname !== '/compare' && (
        <Link to="/compare" className="compare-bar"><span>К сравнению: {compare.length} / 4</span><b>Сравнить</b></Link>
      )}
      <footer className="container footer muted small">
        <span>Умный Шопинг, учебный проект УрФУ</span>
        <span>Цены: Plati.market, SteamBuy и официальные магазины через CheapShark. Данные игр: Steam. Покупка на сайте продавца.</span>
      </footer>
    </>
  )
}
