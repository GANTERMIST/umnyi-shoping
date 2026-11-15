import type { Favorite, Kind, Offer, Profile } from './api'

export const rub = (x: number | null | undefined) =>
  x == null ? '—' : `${Math.round(x).toLocaleString('ru-RU')} ₽`

/** Сумма в своей валюте: рубли у продавцов, доллары у официальных магазинов — без пересчёта. */
export const money = (x: number | null | undefined, currency = 'RUB') =>
  x == null ? '—' : currency === 'USD' ? `$${x.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : rub(x)
export const price = (o: { price: number; currency: string }) => money(o.price, o.currency)
/** Сортировка по цене без смешивания валют: сначала рубли, потом доллары. */
export const byPrice = (a: Offer, b: Offer) => Number(a.currency !== 'RUB') - Number(b.currency !== 'RUB') || a.price - b.price

export const KIND_LABEL: Record<string, string> = {
  ключ: 'Ключ', гифт: 'Гифт', магазин: 'Офиц. магазин', аккаунт: 'Аккаунт', пополнение: 'Пополнение', другое: 'Другое',
}
export const KIND_HINT: Record<string, string> = {
  ключ: 'Код активации — игра навсегда ваша',
  гифт: 'Подарок от продавца в Steam — игра навсегда ваша',
  магазин: 'Покупка напрямую в Steam/GOG/Humble…, цена в долларах, оплата зарубежной картой',
  аккаунт: 'Доступ к чужой учётной записи — игра не ваша, есть риски',
  пополнение: 'Внутриигровая валюта или пополнение кошелька',
  другое: 'Тип не распознан — читайте описание у продавца',
}
export const DEFAULT_KINDS: Kind[] = ['ключ', 'гифт', 'магазин']

export const REGION_LABEL: Record<string, string> = {
  RU: 'Россия', CIS: 'СНГ', GLOBAL: 'Весь мир', KZ: 'Казахстан', TR: 'Турция', EU: 'Европа', NO_RU: 'Не для РФ',
}
export const USER_REGIONS = ['RU', 'KZ', 'TR', 'EU'] as const

export type RegionFit = 'yes' | 'no' | 'unknown'

/** Подходит ли регион активации предложения региону пользователя. */
export function regionFit(o: Offer, userRegion: string): RegionFit {
  const r = o.region
  if (!r) return 'unknown'
  if (r === 'GLOBAL') return 'yes'
  if (r === 'NO_RU') return userRegion === 'RU' ? 'no' : 'unknown'
  if (r === 'CIS') return ['RU', 'KZ'].includes(userRegion) ? 'yes' : 'no'
  return r === userRegion ? 'yes' : 'no'
}

export function regionText(o: Offer, userRegion: string): string {
  const fit = regionFit(o, userRegion)
  if (fit === 'unknown') return o.region === 'NO_RU' ? 'Не для РФ' : 'Регион не указан'
  return `${REGION_LABEL[o.region!] ?? o.region} — ${fit === 'yes' ? 'подходит' : 'не подходит'}`
}

/** «Доставка» цифрового товара: как и когда его получит покупатель. */
export function delivery(o: Offer): string {
  switch (o.kind) {
    case 'магазин': return 'Сразу — игра в библиотеке магазина'
    case 'ключ': return 'Моментально — ключ в заказе'
    case 'гифт': return 'До 30 мин — подарок в Steam'
    case 'аккаунт': return 'Моментально — логин и пароль'
    case 'пополнение': return 'До 1 часа'
    default: return 'Уточните у продавца'
  }
}

/** Условия возврата и гарантии. */
export function guarantee(o: Offer): string {
  if (o.kind === 'магазин') return 'Возврат по правилам магазина (в Steam — 14 дней, если играли меньше 2 ч)'
  if (o.store !== 'plati.market') return `Гарантия магазина ${o.store}: замена или возврат, если товар не пришёл или не активировался`
  const r = o.returns ? ` · возвратов у продавца: ${o.returns}` : ''
  return `Гарантия Plati: спор в заказе, деньги вернут, если товар не подошёл${r}`
}

/** Что пользователь обычно выбирает — по избранному (история предпочтений). */
export function habits(favorites: Favorite[]): { platform: string | null; kind: Kind | null } {
  const top = (key: 'platform' | 'kind') => {
    const cnt: Record<string, number> = {}
    for (const f of favorites) { const v = f[key]; if (v && v !== '?') cnt[v] = (cnt[v] || 0) + 1 }
    const best = Object.entries(cnt).sort((a, b) => b[1] - a[1])[0]
    return best && best[1] >= 2 ? best[0] : null  // привычка — минимум 2 раза
  }
  return { platform: top('platform'), kind: top('kind') as Kind | null }
}

export function trustLabel(o: Offer): string {
  if (o.kind === 'магазин') return 'Официальный магазин'
  if (o.store !== 'plati.market') return `Магазин ${o.store}`
  return o.trusted ? `Надёжный, ${Math.round(o.trust_score * 100)}%` : `Мало отзывов, ${Math.round(o.trust_score * 100)}%`
}

export interface Recommendation {
  offer: Offer
  reasons: string[]
  relaxed: string | null
}

/** Персональная рекомендация: лучшее предложение под профиль пользователя с объяснением. */
export function recommend(offers: Offer[], profile: Profile, favorites: Favorite[] = []): Recommendation | null {
  // чего нет в профиле — берём из истории: что пользователь обычно добавляет в избранное
  const h = habits(favorites)
  const p: Profile = { ...profile, platform: profile.platform || h.platform }
  const fromHistory = !profile.platform && !!h.platform
  const kinds = p.kinds.length ? p.kinds : h.kind && DEFAULT_KINDS.includes(h.kind) ? [h.kind, ...DEFAULT_KINDS.filter(k => k !== h.kind)] : DEFAULT_KINDS
  const base = offers.filter(o => o.trusted && kinds.includes(o.kind) && regionFit(o, p.region) !== 'no')
  const byPlatform = p.platform ? base.filter(o => o.platform === p.platform) : base
  const pool = byPlatform.length ? byPlatform : base
  // бюджет — в рублях: к ценам официальных магазинов в долларах его не применяем
  const inBudget = p.budget ? pool.filter(o => o.currency === 'RUB' && o.price <= p.budget!) : pool
  const list = (inBudget.length ? inBudget : pool).slice().sort(byPrice)
  const best = list[0]
  if (!best) return null
  const reasons: string[] = []
  if (p.budget && best.price <= p.budget) reasons.push(`в бюджете ${rub(p.budget)}`)
  if (p.platform && best.platform === p.platform) reasons.push(fromHistory ? `платформа ${p.platform}, как в вашем избранном` : `платформа ${p.platform}`)
  if (!profile.kinds.length && h.kind === best.kind) reasons.push(`вы чаще выбираете «${KIND_LABEL[best.kind]}»`)
  reasons.push(`тип «${KIND_LABEL[best.kind]}» из вашего списка`)
  const fit = regionFit(best, p.region)
  reasons.push(fit === 'yes' ? `регион подходит (${REGION_LABEL[p.region] ?? p.region})` : 'регион не указан — уточните у продавца')
  reasons.push(best.kind === 'магазин' ? `официальный магазин ${best.store}`
    : best.store !== 'plati.market' ? `магазин ${best.store}` : `надёжный продавец (+${best.reviews_pos} / −${best.reviews_neg})`)
  reasons.push('самая низкая цена среди подходящих')
  let relaxed: string | null = null
  if (p.platform && !byPlatform.length) relaxed = `Для ${p.platform} подходящих нет — показываю другую платформу.`
  else if (p.budget && !inBudget.length) relaxed = `В бюджет ${rub(p.budget)} не уложиться — вот самый дешёвый вариант.`
  return { offer: best, reasons, relaxed }
}

export function timeAgo(iso: string | null): string {
  if (!iso) return ''
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (m < 1) return 'только что'
  if (m < 60) return `${m} мин назад`
  const h = Math.round(m / 60)
  if (h < 24) return `${h} ч назад`
  return `${Math.round(h / 24)} дн назад`
}

/** Вывод для сравнения: что выбрать и почему. */
export function compareVerdict(list: Offer[], userRegion: string): string[] {
  if (list.length < 2) return []
  const ok = list.filter(o => regionFit(o, userRegion) !== 'no')
  const pool = ok.length ? ok : list
  const sorted = pool.slice().sort(byPrice)
  const cheapest = sorted[0]
  const safest = pool.slice().sort((a, b) => b.trust_score - a.trust_score || a.price - b.price)[0]
  const second = sorted.find(o => o.id !== cheapest.id && o.currency === cheapest.currency)
  const name = (o: Offer) => (o.kind === 'магазин' ? o.store : `${KIND_LABEL[o.kind].toLowerCase()} у ${o.seller}`)
  const out = [`Дешевле всего — ${name(cheapest)}: ${price(cheapest)}` +
    (second ? `, на ${money(second.price - cheapest.price, cheapest.currency)} дешевле следующего варианта.` : '.')]
  if (safest.id !== cheapest.id) out.push(`Надёжнее всего — ${name(safest)} (${trustLabel(safest)}), ${price(safest)}` +
    (safest.currency === cheapest.currency ? `, переплата ${money(safest.price - cheapest.price, safest.currency)}.` : ': цена в долларах, с рублями напрямую не сравнить.'))
  if (cheapest.kind === 'аккаунт') out.push('Самый дешёвый вариант — аккаунт: игра не станет вашей. Если нужна навсегда — берите ключ или гифт.')
  const bad = list.filter(o => regionFit(o, userRegion) === 'no')
  if (bad.length) out.push(`Не подходят по региону: ${bad.map(name).join(', ')}.`)
  const pick = cheapest.kind !== 'аккаунт' && cheapest.trusted ? cheapest : safest
  out.push(`Наш выбор: ${name(pick)} за ${price(pick)}.`)
  return out
}
