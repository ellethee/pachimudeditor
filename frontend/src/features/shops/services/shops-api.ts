import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type { IObjectRef, IShopItem, IShopOptions } from '../types/shops'

/** Opzioni per le richieste i cui errori sono mostrati dal chiamante. */
const SILENT = { meta: { autoError: false }, cacheFor: 0 }

/** Client HTTP dell'app, risolto a ogni chiamata. */
function http(base: string) {
  return getUseAlovaInstance()({ url: base }).alova
}

/** I mob con un negozio o con un `shop_id` legacy (`GET /api/content/shops`). */
export async function listShops(): Promise<IShopItem[]> {
  return http('/api/content').Get<IShopItem[]>('/shops', SILENT)
}

/** Tipi di oggetto e messaggi ammessi (`GET /api/content/shops/options`). */
export async function getShopOptions(): Promise<IShopOptions> {
  return http('/api/content').Get<IShopOptions>('/shops/options', SILENT)
}

/** Tutti gli oggetti prototipo, per scegliere le merci (`GET /api/objects`). */
export async function listObjectRefs(): Promise<IObjectRef[]> {
  const data = await http('/api/objects').Get<{ items: IObjectRef[] }>('', { ...SILENT, params: { pageSize: 5000 } })
  return data.items.map(({ vnum, shortDescription }) => ({ vnum, shortDescription }))
}
