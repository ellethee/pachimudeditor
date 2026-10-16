import { defineStore } from 'pinia'
import { ref } from 'vue'
import { localizeEnums } from '../../shared/helpers/enum-labels'
import { fetchEnums } from '../services/lookups-api'
import type { IZoneEnums } from '../types/zones'

/** Store del modulo zone: cache degli enum del backend (si caricano una volta sola). */
export const useZonesStore = defineStore('zones', () => {
  const enums = ref<IZoneEnums | null>(null)
  let pending: Promise<IZoneEnums> | null = null

  /**
   * Restituisce gli enum, caricandoli alla prima chiamata (le chiamate concorrenti condividono la richiesta).
   * @returns le opzioni degli enum
   */
  async function ensureEnums(): Promise<IZoneEnums> {
    if (enums.value) return enums.value
    pending ??= fetchEnums()
      .then((loaded) => (enums.value = localizeEnums(loaded)))
      .finally(() => (pending = null))
    return pending
  }

  return { enums, ensureEnums }
})
