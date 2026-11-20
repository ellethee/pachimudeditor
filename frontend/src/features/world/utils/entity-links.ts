import type { RouteLocationRaw } from 'vue-router'
import type { WorldEntityType } from '../types/world'

/**
 * Destinazione nell'editor di un'entità: `/rooms/:id`, `/mobs/:id`, `/objects/:id` e `/zones/:id` sono le pagine di
 * dettaglio (maschera di modifica inline). I vecchi deep-link `?roomId=`, `?mobId=` e `?objectId=` delle liste e
 * `/zones?zoneId=` vi rimandano ancora.
 *
 * @param type - tipo di entità
 * @param id - id della riga
 * @param zoneId - id della zona proprietaria (per le zone è la zona stessa)
 * @param resets - per una zona, apre lo script di reset invece dell'elenco
 */
export function entityLocation(type: WorldEntityType, id: number, zoneId: number, resets = false): RouteLocationRaw {
  switch (type) {
    case 'room':
      return { path: `/rooms/${id}` }
    case 'mob':
      return { path: `/mobs/${id}` }
    case 'object':
      return { path: `/objects/${id}` }
    case 'zone':
      return resets ? { path: `/zones/${id}`, query: { tab: 'resets' } } : { path: `/zones/${id}` }
  }
}
