import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type { IZoneEnums, ILookups } from '../types/zones'

/** Elemento minimo restituito dagli elenchi di stanze/mob/oggetti. */
interface ILookupSource {
  vnum: number
  name?: string
  shortDescription?: string
}

/**
 * Legge tutti gli elementi di una risorsa (senza paginazione) e li riduce a `vnum -> nome`.
 * @param url endpoint della risorsa (`/api/rooms`, `/api/mobs`, `/api/objects`)
 */
async function loadVnumNames(url: string): Promise<Map<number, string>> {
  const { alova } = getUseAlovaInstance()({ url })
  const page = await alova.Get<{ items: ILookupSource[] }>('')
  return new Map(page.items.map((item) => [item.vnum, item.name ?? item.shortDescription ?? '']))
}

/** Carica in parallelo i vnum noti di stanze, mob e oggetti (prototipi) con i loro nomi. */
export async function loadLookups(): Promise<ILookups> {
  const [room, mob, object] = await Promise.all([
    loadVnumNames('/api/rooms'),
    loadVnumNames('/api/mobs'),
    loadVnumNames('/api/objects'),
  ])
  return { room, mob, object }
}

/** Legge le opzioni degli enum del backend (`GET /api/meta/enums`). */
export async function fetchEnums(): Promise<IZoneEnums> {
  const { alova } = getUseAlovaInstance()({ url: '/api/meta' })
  return alova.Get<IZoneEnums>('/enums')
}
