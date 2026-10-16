import { defineStore } from 'pinia'
import { ref } from 'vue'
import { localizeEnums } from '../../shared/helpers/enum-labels'
import { getEnums, listZones } from '../services/rooms-api'
import type { IEnumOptions, IZoneRef } from '../types/rooms'

/**
 * Stato condiviso della feature stanze: enum e zone (caricati una volta), zona selezionata
 * (condivisa tra lista e mappa).
 */
export const useRoomsStore = defineStore('rooms', () => {
  const enums = ref<IEnumOptions | null>(null)
  const zones = ref<IZoneRef[]>([])
  const selectedZoneId = ref<number | null>(null)

  /** Carica le enum se non ancora presenti. */
  async function ensureEnums(): Promise<IEnumOptions> {
    if (!enums.value) enums.value = localizeEnums(await getEnums())
    return enums.value
  }

  /** Ricarica le zone; se nessuna è selezionata (o non esiste più) seleziona la prima. */
  async function loadZones(): Promise<void> {
    zones.value = await listZones()
    if (!zones.value.some((zone) => zone.id === selectedZoneId.value)) {
      selectedZoneId.value = zones.value[0]?.id ?? null
    }
  }

  return { enums, zones, selectedZoneId, ensureEnums, loadZones }
})
