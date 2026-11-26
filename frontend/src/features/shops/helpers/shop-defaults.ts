import type { IShopData } from '../types/shops'

/** Lingue dei testi propri del negozio (le cartelle `locales/` del gioco). */
export const SHOP_LANGS = ['it', 'en'] as const

/** Negozio nuovo: gli stessi valori di `pachimud new shop`. */
export function newShop(): IShopData {
  return {
    produces: [],
    trades: [],
    profit_buy: 1.2,
    profit_sell: 0.4,
    room: null,
    open1: 7,
    close1: 21,
    open2: 0,
    close2: 0,
    no_money_reaction: 'puke',
    attacked_reaction: 'warn',
    messages: {},
    handler: null,
    hours: [],
    inventory_closed: false,
  }
}

/**
 * Copia di un negozio con i campi mancanti ai valori di default del gioco (il backend restituisce tutti i campi, ma un `extra` vecchio no).
 * @param raw valore di `extra.shop` (anche assente)
 * @returns il negozio, o `null` se il mob non è un negoziante
 */
export function normalizeShop(raw: unknown): IShopData | null {
  if (raw === null || typeof raw !== 'object') return null
  const base = newShop()
  const shop = { ...base, ...(raw as Partial<IShopData>) }
  shop.messages = JSON.parse(JSON.stringify(shop.messages ?? {})) as IShopData['messages']
  shop.produces = [...(shop.produces ?? [])]
  shop.trades = [...(shop.trades ?? [])]
  return shop
}

/**
 * Problemi di un negozio, come messaggi i18n (vuoto se valido).
 * @param shop negozio
 * @returns chiavi i18n sotto `shops.errors`
 */
export function shopProblems(shop: IShopData): string[] {
  const problems: string[] = []
  if (shop.produces.length > 5) problems.push('tooManyProduces')
  if (shop.trades.length > 5) problems.push('tooManyTrades')
  if (!(shop.profit_buy >= 0) || !(shop.profit_sell >= 0)) problems.push('profit')
  for (const hour of [shop.open1, shop.open2]) if (!Number.isInteger(hour) || hour < 0 || hour > 23) problems.push('hours')
  for (const hour of [shop.close1, shop.close2]) if (!Number.isInteger(hour) || hour < 0 || hour > 28) problems.push('hours')
  if (shop.hours.length > 2 || shop.hours.some((h) => !/^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$/.test(h))) problems.push('hours')
  if (shop.room !== null && (!Number.isInteger(shop.room) || shop.room < 0)) problems.push('room')
  return [...new Set(problems)]
}
