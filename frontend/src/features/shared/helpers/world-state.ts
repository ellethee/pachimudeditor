import { computed, ref } from 'vue'
import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type {
  IExtraFieldDescriptor,
  IFieldDescriptor,
  IWorld,
  IWorldResource,
  IWorldCapabilities,
  WorldCapability,
} from '../types/worlds'

/** Chiave del localStorage con il mondo scelto (comodita' per-viewer: mai stato affidabile). */
const STORAGE_KEY = 'pachimud-webeditor-world'

/** Legge il mondo salvato (assente o localStorage non disponibile: `null`). */
function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

/**
 * Salva (o cancella, con `null`) il mondo scelto.
 *
 * @param id - id del mondo
 */
function writeStored(id: string | null): void {
  try {
    if (id === null) window.localStorage.removeItem(STORAGE_KEY)
    else window.localStorage.setItem(STORAGE_KEY, id)
  } catch {
    // localStorage non disponibile: la scelta vale solo per questa sessione
  }
}

/** Mondi configurati (da `GET /api/worlds`). */
const worlds = ref<IWorld[]>([])
/** `true` dopo il primo caricamento riuscito dell'elenco. */
const loaded = ref(false)
/** Id del mondo scelto dall'utente (`null` = default del backend, nessun `X-World`). */
const chosenId = ref<string | null>(readStored())
let pending: Promise<void> | null = null

/** Mondo attivo: quello scelto se esiste, altrimenti il default (o il primo). */
const activeWorld = computed<IWorld | undefined>(
  () =>
    worlds.value.find((world) => world.id === chosenId.value) ??
    worlds.value.find((world) => world.default) ??
    worlds.value[0],
)

/**
 * Id da inviare in `X-World`: la scelta dell'utente, anche prima che l'elenco sia arrivato; `null` se non
 * c'è una scelta valida (il backend usa il suo default).
 */
export function currentWorldHeader(): string | null {
  if (loaded.value && !worlds.value.some((world) => world.id === chosenId.value)) return null
  return chosenId.value
}

/**
 * Carica l'elenco dei mondi (una volta; le chiamate concorrenti condividono la richiesta). Un errore non
 * viene mostrato né propagato: l'editor resta usabile con le capability di default (tutto visibile).
 */
export function ensureWorlds(): Promise<void> {
  if (loaded.value) return Promise.resolve()
  pending ??= getUseAlovaInstance()({ url: '/api/worlds' })
    .alova.Get<IWorld[]>('', { cacheFor: 0, meta: { autoError: false, spinner: false } })
    .then((list) => {
      worlds.value = list
      if (!list.some((world) => world.id === chosenId.value)) {
        chosenId.value = null
        writeStored(null)
      }
      loaded.value = true
    })
    .catch(() => undefined)
    .finally(() => (pending = null))
  return pending
}

/**
 * Sceglie il mondo attivo e lo ricorda. Dopo la scelta i dati vanno ricaricati (il selettore ricarica la pagina).
 *
 * @param id - id del mondo
 */
export function selectWorld(id: string): void {
  chosenId.value = id
  writeStored(id)
}

/**
 * Stato del mondo attivo per i componenti (reattivo, condiviso).
 *
 * @returns mondi, mondo attivo, capability, sola lettura e accesso ai descrittori dei campi
 */
export function useWorld() {
  const capabilities = computed<IWorldCapabilities | undefined>(() => activeWorld.value?.capabilities)
  const readOnly = computed(() => capabilities.value?.readOnly === true)
  const kind = computed(() => activeWorld.value?.kind ?? 'pachimud')

  /**
   * `true` se il mondo supporta la funzione (finché l'elenco non è caricato tutto risulta supportato,
   * così il menu non lampeggia e un errore di rete non nasconde l'editor).
   *
   * @param capability - capability richiesta
   */
  function supports(capability: WorldCapability): boolean {
    return !loaded.value || capabilities.value?.[capability] !== false
  }

  /**
   * Descrittori dei campi di una risorsa (vuoti se il mondo non li dichiara).
   *
   * @param resource - tipo di risorsa (`zone`, `room`, `mob`, `object`, ...)
   */
  function fieldsOf(resource: string): IFieldDescriptor[] {
    return activeWorld.value?.resources.find((item) => item.type === resource)?.fields ?? []
  }

  /**
   * Descrittore di un campo dichiarato dal mondo (`describe()`): sola lettura, non supportato, enum.
   *
   * @param resource - tipo di risorsa
   * @param name - nome del campo
   */
  function fieldOf(resource: string, name: string): IFieldDescriptor | undefined {
    return fieldsOf(resource).find((field) => field.name === name)
  }

  /**
   * Risorsa dichiarata dal mondo (campi, chiavi di `extra`, flag di creazione).
   *
   * @param resource - tipo di risorsa
   */
  function resourceOf(resource: string): IWorldResource | undefined {
    return activeWorld.value?.resources.find((item) => item.type === resource)
  }

  /**
   * Le chiavi di `extra` dichiarate dal mondo per la risorsa (vuote in pachimud).
   *
   * @param resource - tipo di risorsa
   */
  function extraFieldsOf(resource: string): IExtraFieldDescriptor[] {
    return resourceOf(resource)?.extraFields ?? []
  }

  /**
   * `true` se il mondo dichiara il campo `extra` per la risorsa (editor dei campi specifici del MUD).
   *
   * @param resource - tipo di risorsa
   */
  function declaresExtra(resource: string): boolean {
    return fieldsOf(resource).some((field) => field.name === 'extra') || extraFieldsOf(resource).length > 0
  }

  return {
    worlds,
    loaded,
    activeWorld,
    capabilities,
    readOnly,
    kind,
    supports,
    fieldsOf,
    fieldOf,
    resourceOf,
    extraFieldsOf,
    declaresExtra,
  }
}
