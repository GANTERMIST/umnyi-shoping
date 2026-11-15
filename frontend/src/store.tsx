// Состояние приложения: пользователь, профиль, избранное, сравнение, тема.
// Без входа всё хранится в localStorage; после входа — синхронизируется с сервером.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, type Favorite, type Me, type Offer, type Profile, type Viewed } from './api'

const DEFAULT_PROFILE: Profile = { budget: null, platform: null, kinds: [], region: 'RU', genres: [] }
const MAX_COMPARE = 4

function load<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key)
    return v ? (JSON.parse(v) as T) : fallback
  } catch {
    return fallback
  }
}
function save(key: string, v: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(v))
  } catch {
    /* приватный режим */
  }
}

interface Ctx {
  user: Me['user'] | null
  profile: Profile
  favorites: Favorite[]
  compare: Offer[]
  prices: Record<string, number>  // текущие цены избранного из базы
  changed: number                 // у скольких товаров в избранном изменилась цена
  reached: number                 // у скольких достигнута целевая цена
  viewed: Viewed[]                // история просмотров (Ф27)
  addViewed: (v: Omit<Viewed, 'at'>) => void
  setTarget: (id: string, price: number | null) => void
  theme: 'light' | 'dark'
  setTheme: (t: 'light' | 'dark') => void
  setProfile: (p: Profile) => void
  isFav: (id: string) => boolean
  toggleFav: (o: Offer, appid?: number | null) => void
  removeFav: (id: string) => void
  inCompare: (id: string) => boolean
  toggleCompare: (o: Offer) => string | null
  clearCompare: () => void
  signedIn: (me: Me) => void
  signOut: () => Promise<void>
  refreshPrices: () => Promise<void>
}

const AppCtx = createContext<Ctx | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me['user'] | null>(null)
  const [profile, setProfileState] = useState<Profile>(() => ({ ...DEFAULT_PROFILE, ...load('us.profile', {}) }))
  const [favorites, setFavorites] = useState<Favorite[]>(() => load('us.favorites', []))
  const [compare, setCompare] = useState<Offer[]>(() => load('us.compare', []))
  const [prices, setPrices] = useState<Record<string, number>>({})
  const [viewed, setViewed] = useState<Viewed[]>(() => load('us.viewed', []))
  const [theme, setThemeState] = useState<'light' | 'dark'>(() => load('us.theme', 'light'))

  useEffect(() => { save('us.profile', profile) }, [profile])
  useEffect(() => { save('us.favorites', favorites) }, [favorites])
  useEffect(() => { save('us.compare', compare) }, [compare])
  useEffect(() => { save('us.viewed', viewed) }, [viewed])
  useEffect(() => {
    save('us.theme', theme)
    document.documentElement.dataset.theme = theme
  }, [theme])

  // при загрузке — восстановить сессию по cookie
  useEffect(() => {
    api.me().then(me => signedIn(me)).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const refreshPrices = useCallback(async () => {
    if (!favorites.length) return setPrices({})
    try {
      const cur = await api.current(favorites.map(f => f.offer_id))
      setPrices(Object.fromEntries(cur.map(o => [o.id, o.price])))
    } catch {
      /* без сервера — просто не показываем изменения */
    }
  }, [favorites])
  useEffect(() => { refreshPrices() }, [refreshPrices])

  const pushFavorites = (f: Favorite[]) => {
    setFavorites(f)
    if (user) api.putFavorites(f).catch(() => {})
  }

  const signedIn = (me: Me) => {
    setUser(me.user)
    // объединяем избранное с этого устройства и с сервера
    const local: Favorite[] = load('us.favorites', [])
    const merged = [...me.favorites]
    for (const f of local) if (!merged.some(m => m.offer_id === f.offer_id)) merged.push(f)
    setFavorites(merged)
    if (merged.length !== me.favorites.length) api.putFavorites(merged).catch(() => {})
    const serverHasProfile = me.profile.budget || me.profile.platform || me.profile.kinds.length
    if (serverHasProfile) setProfileState({ ...DEFAULT_PROFILE, ...me.profile })
    else api.putProfile(load('us.profile', DEFAULT_PROFILE)).catch(() => {})
  }

  const value: Ctx = {
    user, profile, favorites, compare, prices, theme,
    changed: favorites.filter(f => prices[f.offer_id] != null && prices[f.offer_id] !== f.price).length,
    reached: favorites.filter(f => f.target_price && prices[f.offer_id] != null && prices[f.offer_id] <= f.target_price).length,
    viewed,
    addViewed: v => setViewed(old => [{ ...v, at: new Date().toISOString() }, ...old.filter(x => x.appid !== v.appid)].slice(0, 12)),
    setTarget: (id, price) => pushFavorites(favorites.map(f => (f.offer_id === id ? { ...f, target_price: price } : f))),
    setTheme: setThemeState,
    setProfile: p => {
      setProfileState(p)
      if (user) api.putProfile(p).catch(() => {})
    },
    isFav: id => favorites.some(f => f.offer_id === id),
    toggleFav: (o, appid = null) => {
      if (favorites.some(f => f.offer_id === o.id)) pushFavorites(favorites.filter(f => f.offer_id !== o.id))
      else pushFavorites([...favorites, { offer_id: o.id, title: o.title, price: o.price, appid, added_at: new Date().toISOString(),
        kind: o.kind, platform: o.platform }])
    },
    removeFav: id => pushFavorites(favorites.filter(f => f.offer_id !== id)),
    inCompare: id => compare.some(c => c.id === id),
    toggleCompare: o => {
      if (compare.some(c => c.id === o.id)) {
        setCompare(compare.filter(c => c.id !== o.id))
        return null
      }
      if (compare.length >= MAX_COMPARE) return `Сравнить можно не больше ${MAX_COMPARE} предложений`
      setCompare([...compare, o])
      return null
    },
    clearCompare: () => setCompare([]),
    signedIn,
    signOut: async () => {
      await api.logout().catch(() => {})
      setUser(null)
    },
    refreshPrices,
  }
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>
}

export function useApp(): Ctx {
  const c = useContext(AppCtx)
  if (!c) throw new Error('AppProvider не подключён')
  return c
}
