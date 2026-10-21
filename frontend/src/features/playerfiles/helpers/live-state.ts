import { computed, ref } from 'vue'
import { ResponseError } from '@ilpachi/use-alova'
import { useWorld } from '../../shared/helpers/world-state'
import { getLiveStatus } from '../services/live-api'
import type { ILiveStatus } from '../types/live'

/** Ultimo stato noto del canale (condiviso fra pagina e dialog). */
const status = ref<ILiveStatus>()
/** `false` dopo un 401/403: l'utente non è superuser, la parte live non si mostra. */
const allowed = ref(true)

/**
 * Rilegge lo stato del canale. Mai un errore: un 403 spegne la parte live, altri guasti lasciano lo stato «sconosciuto»
 * (il ripiego sui file resta sempre disponibile).
 */
export async function refreshLiveStatus(): Promise<void> {
  try {
    status.value = await getLiveStatus()
    allowed.value = true
  } catch (e) {
    status.value = undefined
    if (e instanceof ResponseError && (e.status === 401 || e.status === 403)) allowed.value = false
  }
}

/**
 * Stato del canale live per i componenti: la parte live è disponibile solo con la capability `supportsLive` del mondo e per un superuser.
 *
 * @returns stato, disponibilità, possibilità di scrivere e rilettura
 */
export function useLive() {
  const { capabilities } = useWorld()
  /** Il mondo ha il canale e l'utente può usarlo. */
  const enabled = computed(() => capabilities.value?.supportsLive === true && allowed.value)
  /** Il MUD risponde adesso. */
  const connected = computed(() => enabled.value && status.value?.state === 'connected')
  /** Si può scrivere dal canale: MUD raggiungibile, classe `write` attiva nel MUD e mondo non in sola lettura. */
  const canWrite = computed(
    () => connected.value && (status.value?.classes ?? []).includes('write') && capabilities.value?.readOnly !== true,
  )
  return { status, enabled, connected, canWrite, refresh: refreshLiveStatus }
}
