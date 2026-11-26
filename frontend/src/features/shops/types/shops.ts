/** Tipi dei negozi (`/api/content/shops`) e del campo `extra.shop` di un mob pachimud. */

/** Il campo `shop:` di un mob come arriva in `extra.shop` (chiavi del file YAML). */
export interface IShopData {
  produces: number[]
  trades: string[]
  profit_buy: number
  profit_sell: number
  room: number | null
  open1: number
  close1: number
  open2: number
  close2: number
  no_money_reaction: 'puke' | 'grin' | 'none'
  attacked_reaction: 'warn' | 'insult' | 'none'
  /** Testi propri: chiave del messaggio -> lingua -> testo (`{player}`, `{coins}`). */
  messages: Record<string, Record<string, string>>
  handler: string | null
  /** Fasce `hh:mm-hh:mm` in ora di gioco (al massimo 2): valgono al posto di open/close. */
  hours: string[]
  inventory_closed: boolean
}

/** Un oggetto sempre in vendita. */
export interface IShopGood {
  vnum: number
  /** `null` se l'oggetto non esiste. */
  name: string | null
}

/** Una riga dell'elenco dei negozi. */
export interface IShopItem {
  vnum: number
  name: string
  zoneId: number
  zoneName: string
  hasShop: boolean
  /** `shop_id` dei vecchi file: il gioco lo ignora. */
  legacyShopId: string | null
  produces: IShopGood[]
  trades: string[]
  profitBuy: number
  profitSell: number
  room: number | null
  roomName: string | null
  open1: number
  close1: number
  open2: number
  close2: number
  handler: string | null
  hours?: string[]
  inventoryClosed?: boolean
}

/** Valori ammessi dai campi del negozio. */
export interface IShopOptions {
  objectTypes: string[]
  messageKeys: string[]
}

/** Oggetto selezionabile fra le merci. */
export interface IObjectRef {
  vnum: number
  shortDescription: string
}
