import type { RouteLocationRaw } from 'vue-router'
import type { WorldEntityType } from '../types/world'

/**
 * Destinazione nell'editor di un'entità. Convenzione query-param, letta da tutte le pagine:
 * `/rooms?zoneId=&roomId=`, `/mobs?zoneId=&mobId=` e `/objects?zoneId=&objectId=` selezionano la zona e
 * aprono l'editor dell'entità; `/zones?zoneId=` apre l'editor della zona; `/rooms/map?zoneId=` mostra la
 * mappa di quella zona.
 *
 * @param type - tipo di entità
 * @param id - id della riga
 * @param zoneId - id della zona proprietaria (per le zone è la zona stessa)
 * @param resets - per una zona, apre lo script di reset invece dell'elenco
 */
export function entityLocation(type: WorldEntityType, id: number, zoneId: number, resets = false): RouteLocationRaw {
  switch (type) {
    case 'room':
      return { path: '/rooms', query: { zoneId: String(zoneId), roomId: String(id) } }
    case 'mob':
      return { path: '/mobs', query: { zoneId: String(zoneId), mobId: String(id) } }
    case 'object':
      return { path: '/objects', query: { zoneId: String(zoneId), objectId: String(id) } }
    case 'zone':
      return resets ? { path: `/zones/${id}/resets` } : { path: '/zones', query: { zoneId: String(id) } }
  }
}
