// Клиент API бэкенда. Типы повторяют app/schemas.py.

export type Kind = 'ключ' | 'гифт' | 'магазин' | 'аккаунт' | 'пополнение' | 'другое'

export interface Offer {
  id: string
  store: string
  title: string
  price: number
  currency: string
  url: string
  seller: string
  seller_rating: number
  sold: number
  reviews_pos: number
  reviews_neg: number
  returns: number
  kind: Kind
  platform: string
  trusted: boolean
  trust_score: number
  image: string | null
  region: string | null
  old_price: number | null
  note: string | null
}

export interface Game {
  appid: number
  name: string
  genres: string[]
  image: string | null
  metacritic: number | null
  release: string | null
  steam_review_pct: number | null
  steam_reviews: number | null
}

export interface SearchRes {
  query: string
  game: Game | null
  total_found: number
  matched: number
  facets: { kinds: Record<string, number>; platforms: Record<string, number> }
  offers: Offer[]
  warnings: string[]
}

export interface GameCard {
  game: Game
  offers: Offer[]
  best: Record<string, Offer>
}

export interface CatalogItem {
  appid: number
  name: string
  image: string | null
  genres: string[]
  metacritic: number | null
  steam_review_pct: number | null
  best_price: number | null
  best_kind: string | null
  official_price: number | null
  offers: number
  savings_pct: number | null
  updated_at: string | null
}

export interface Profile {
  budget: number | null
  platform: string | null
  kinds: Kind[]
  region: string
  genres: string[]
}

export interface Favorite {
  offer_id: string
  title: string
  price: number
  appid: number | null
  added_at: string
  kind?: string | null
  platform?: string | null
  target_price?: number | null
  currency?: string
}

export interface Viewed {
  appid: number
  name: string
  image: string | null
  genres: string[]
  at: string
}

export interface Me {
  user: { id: number; email: string; name: string | null }
  profile: Profile
  favorites: Favorite[]
  token?: string | null
}

export interface Nlu {
  intent: 'buy' | 'recommend' | 'review' | 'compare' | 'faq' | 'greet' | 'other'
  confidence: number
  kind: Kind | null
  platform: string | null
  game: string | null
  query: string | null
  max_price: number | null
  genre: string | null
  genre_text: string | null
}

export interface AssistantRes {
  answer: string
  offers: Offer[]
  game: Game | null
  engine: 'model' | 'rules' | 'claude'
  nlu: Nlu | null
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

const BASE: string = import.meta.env.VITE_API_URL ?? ''

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response
  try {
    r = await fetch(BASE + path, {
      credentials: 'include',
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    })
  } catch {
    throw new ApiError(0, 'Сервер недоступен. Проверьте, что бэкенд запущен (run.bat).')
  }
  if (!r.ok) {
    let msg = `Ошибка ${r.status}`
    try {
      const d = await r.json()
      if (typeof d.detail === 'string') msg = d.detail
      else if (Array.isArray(d.detail) && d.detail[0]?.msg) msg = humanize(d.detail[0])
    } catch {
      /* не JSON */
    }
    throw new ApiError(r.status, msg)
  }
  return r.json()
}

function humanize(e: { loc?: string[]; msg: string }): string {
  const field = e.loc?.[e.loc.length - 1]
  if (field === 'email') return 'Проверьте адрес почты'
  if (field === 'password') return 'Пароль — не короче 8 символов'
  if (field === 'q') return 'Запрос — от 2 до 100 символов'
  return e.msg
}

const json = (body: unknown, method = 'POST'): RequestInit => ({ method, body: JSON.stringify(body) })

export const api = {
  search: (q: string, limit = 200) => req<SearchRes>(`/api/search?${new URLSearchParams({ q, limit: String(limit) })}`),
  game: (appid: number) => req<GameCard>(`/api/games/${appid}`),
  history: (id: string) => req<{ offer_id: string; points: { ts: string; price: number }[] }>(
    `/api/offers/${encodeURIComponent(id)}/history`),
  current: (ids: string[]) => req<Offer[]>('/api/offers/current', json({ ids })),
  catalog: (limit = 100) => req<CatalogItem[]>(`/api/catalog?limit=${limit}`),
  deals: (limit = 8) => req<CatalogItem[]>(`/api/deals?limit=${limit}`),
  similar: (appid: number) => req<CatalogItem[]>(`/api/games/${appid}/similar`),
  feedback: (helpful: boolean, where: string, offer_id?: string, query?: string) =>
    req<{ ok: boolean }>('/api/feedback', json({ helpful, where, offer_id, query })),
  feedbackStats: () => req<{ total: number; helpful: number; helpful_pct: number | null }>('/api/feedback/stats'),
  stores: () => req<{ name: string; api_type: string; offers: number }[]>('/api/stores'),
  health: () => req<{ ok: boolean; assistant: string }>('/api/health'),
  assistant: (message: string, history: { role: 'user' | 'assistant'; text: string }[], profile: Profile | null) =>
    req<AssistantRes>('/api/assistant', json({ message, history, profile })),
  register: (email: string, password: string, name?: string) => req<Me>('/api/auth/register', json({ email, password, name })),
  login: (email: string, password: string) => req<Me>('/api/auth/login', json({ email, password })),
  logout: () => req<{ ok: boolean }>('/api/auth/logout', json({})),
  telegramConfig: () => req<{ bot: string | null }>('/api/auth/telegram/config'),
  telegram: (user: TelegramUser) => req<Me>('/api/auth/telegram', json(user)),
  telegramPoll: (code: string) => req<Me | { pending: true }>('/api/auth/telegram/poll', json({ code })),
  me: () => req<Me>('/api/me'),
  putProfile: (p: Profile) => req<Me>('/api/me/profile', json(p, 'PUT')),
  putFavorites: (f: Favorite[]) => req<Me>('/api/me/favorites', json(f, 'PUT')),
}

/** Что отдаёт Telegram Login Widget в onauth. */
export interface TelegramUser {
  id: number; first_name?: string; last_name?: string; username?: string; photo_url?: string; auth_date: number; hash: string
}
