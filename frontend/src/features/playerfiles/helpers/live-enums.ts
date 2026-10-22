import { getEnums } from '../../objects/services/objects-api'
import { localizeEnums } from '../../shared/helpers/enum-labels'
import type { IEnumOpt } from './live-item'

/**
 * Enum del mondo attivo (`/api/meta/enums`) per etichettare flag, affect e slot. Un errore vale «nessun enum»: la UI ripiega sui numeri.
 *
 * @returns mappa nome → opzioni (vuota se non disponibile)
 */
export async function loadLiveEnums(): Promise<Record<string, IEnumOpt[]>> {
  try {
    return localizeEnums(await getEnums()) as unknown as Record<string, IEnumOpt[]>
  } catch {
    return {}
  }
}
