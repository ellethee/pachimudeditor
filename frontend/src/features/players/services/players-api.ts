import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type {
  IAccount,
  IAccountInput,
  ICharacterDetail,
  ICharacterPatch,
  IInventoryItem,
  IObjectRef,
  IPage,
  IPlayerLookups,
  IRoomRef,
} from '../types/players'

/**
 * Client HTTP dell'app (@ilpachi/use-alova): auth, refresh e spinner sono già gestiti. Risolto a ogni
 * chiamata per non dipendere dall'ordine dei boot.
 *
 * @param url - base URL delle richieste
 */
function http(url: string) {
  return getUseAlovaInstance()({ url }).alova
}

/** Opzioni comuni: nessuna cache, gli errori li mostra la UI (`describeError`). */
const OPTS = { cacheFor: 0, meta: { autoError: false } } as const

/** Endpoint base della tabella account. */
export const ACCOUNTS_URL = '/api/players/accounts'
/** Endpoint base della tabella personaggi. */
export const CHARACTERS_URL = '/api/players/characters'

/** Elenchi per i form (sesso, posizione, razze, classi). */
export async function getLookups(): Promise<IPlayerLookups> {
  return http('/api/players').Get<IPlayerLookups>('/lookups', OPTS)
}

/**
 * Tutti gli account (senza `page`/`pageSize` non si pagina), per le select.
 */
export async function listAllAccounts(): Promise<IAccount[]> {
  const data = await http(ACCOUNTS_URL).Get<IPage<IAccount> | IAccount[]>('', OPTS)
  return Array.isArray(data) ? data : data.items
}

/**
 * Crea un account.
 *
 * @param body - username, password in chiaro ed email opzionale
 */
export async function createAccount(body: IAccountInput): Promise<IAccount> {
  return http(ACCOUNTS_URL).Post<IAccount>('', body, OPTS)
}

/**
 * Modifica l'email di un account (`null` la rimuove).
 *
 * @param id - id account
 * @param email - nuova email
 */
export async function updateAccountEmail(id: number, email: string | null): Promise<IAccount> {
  return http(ACCOUNTS_URL).Put<IAccount>(`/${id}`, { email }, OPTS)
}

/**
 * Banna o riabilita un account.
 *
 * @param id - id account
 * @param banned - `true` per bannare
 */
export async function setAccountBan(id: number, banned: boolean): Promise<IAccount> {
  return http(ACCOUNTS_URL).Post<IAccount>(`/${id}/${banned ? 'ban' : 'unban'}`, undefined, OPTS)
}

/**
 * Imposta una nuova password.
 *
 * @param id - id account
 * @param password - password in chiaro (min 8 caratteri)
 */
export async function setAccountPassword(id: number, password: string): Promise<IAccount> {
  return http(ACCOUNTS_URL).Post<IAccount>(`/${id}/password`, { password }, OPTS)
}

/**
 * Elimina un account.
 *
 * @param id - id account
 * @param cascade - elimina anche personaggi e inventari
 */
export async function deleteAccount(id: number, cascade: boolean): Promise<void> {
  await http(ACCOUNTS_URL).Delete<void>(`/${id}`, undefined, { ...OPTS, params: { cascade } })
}

/**
 * Scheda completa di un personaggio.
 *
 * @param id - id personaggio
 */
export async function getCharacter(id: number): Promise<ICharacterDetail> {
  return http(CHARACTERS_URL).Get<ICharacterDetail>(`/${id}`, OPTS)
}

/**
 * Aggiorna (patch parziale) un personaggio.
 *
 * @param id - id personaggio
 * @param patch - campi da modificare
 */
export async function updateCharacter(id: number, patch: ICharacterPatch): Promise<ICharacterDetail> {
  return http(CHARACTERS_URL).Put<ICharacterDetail>(`/${id}`, patch, OPTS)
}

/**
 * Teletrasporta un personaggio in una stanza.
 *
 * @param id - id personaggio
 * @param roomId - id (non vnum) della stanza
 */
export async function teleportCharacter(id: number, roomId: number): Promise<ICharacterDetail> {
  return http(CHARACTERS_URL).Post<ICharacterDetail>(`/${id}/teleport`, { roomId }, OPTS)
}

/**
 * Elimina un personaggio.
 *
 * @param id - id personaggio
 * @param cascade - elimina anche l'inventario
 */
export async function deleteCharacter(id: number, cascade: boolean): Promise<void> {
  await http(CHARACTERS_URL).Delete<void>(`/${id}`, undefined, { ...OPTS, params: { cascade } })
}

/**
 * Inventario di un personaggio (portati, equipaggiati, contenuti).
 *
 * @param characterId - id personaggio
 */
export async function listInventory(characterId: number): Promise<IInventoryItem[]> {
  return http(CHARACTERS_URL).Get<IInventoryItem[]>(`/${characterId}/inventory`, OPTS)
}

/**
 * Aggiunge un'istanza di un prototipo all'inventario.
 *
 * @param characterId - id personaggio
 * @param prototypeId - id del prototipo oggetto
 */
export async function addInventoryItem(characterId: number, prototypeId: number): Promise<IInventoryItem> {
  return http(CHARACTERS_URL).Post<IInventoryItem>(`/${characterId}/inventory`, { prototypeId }, OPTS)
}

/**
 * Imposta o toglie lo slot di equipaggiamento di un oggetto.
 *
 * @param characterId - id personaggio
 * @param itemId - id istanza
 * @param equippedSlot - slot oppure `null`
 */
export async function setItemSlot(
  characterId: number,
  itemId: number,
  equippedSlot: string | null,
): Promise<IInventoryItem> {
  return http(CHARACTERS_URL).Put<IInventoryItem>(`/${characterId}/inventory/${itemId}`, { equippedSlot }, OPTS)
}

/**
 * Rimuove un oggetto (e il suo contenuto) dall'inventario.
 *
 * @param characterId - id personaggio
 * @param itemId - id istanza
 */
export async function removeInventoryItem(characterId: number, itemId: number): Promise<void> {
  await http(CHARACTERS_URL).Delete<void>(`/${characterId}/inventory/${itemId}`, undefined, OPTS)
}

/**
 * Cerca stanze per il teletrasporto (ricerca server-side su nome/vnum).
 *
 * @param search - testo cercato
 */
export async function searchRooms(search: string): Promise<IRoomRef[]> {
  const data = await http('/api/rooms').Get<IPage<IRoomRef>>('', {
    ...OPTS,
    params: { page: 1, pageSize: 30, search },
  })
  return data.items
}

/**
 * Cerca prototipi di oggetto per l'aggiunta all'inventario.
 *
 * @param search - testo cercato
 */
export async function searchObjects(search: string): Promise<IObjectRef[]> {
  const data = await http('/api/objects').Get<IPage<IObjectRef>>('', {
    ...OPTS,
    params: { page: 1, pageSize: 30, search },
  })
  return data.items
}
