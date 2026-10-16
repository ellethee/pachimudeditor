import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type { ContentKind, IContentItem, IContentOptions, IContentStatus } from '../types/content'

/** Opzioni per le richieste i cui errori sono mostrati dal chiamante (niente dialogo globale). */
const SILENT = { meta: { autoError: false }, cacheFor: 0 }

/**
 * Client HTTP dell'app (@ilpachi/use-alova): Authorization, refresh del token e busta di risposta
 * sono già gestiti. Risolto a ogni chiamata per non dipendere dall'ordine dei boot.
 */
function http() {
  return getUseAlovaInstance()({ url: '/api/content' }).alova
}

/**
 * Elenco di razze o classi (anche disattivate o non valide).
 * @param kind tipo di contenuto
 */
export async function listContent<T extends IContentItem>(kind: ContentKind): Promise<T[]> {
  return http().Get<T[]>(`/${kind}`, SILENT)
}

/**
 * Crea una razza/classe (`POST /api/content/{kind}`).
 * @param kind tipo di contenuto
 * @param body campi del file YAML (camelCase)
 */
export async function createContent<T extends IContentItem>(kind: ContentKind, body: object): Promise<T> {
  return http().Post<T>(`/${kind}`, body, SILENT)
}

/**
 * Aggiorna una razza/classe: il backend applica solo i campi inviati e preserva commenti e formato.
 * @param kind tipo di contenuto
 * @param id id (nome del file senza estensione)
 * @param body campi del file YAML (camelCase), compreso l'id
 */
export async function updateContent<T extends IContentItem>(kind: ContentKind, id: string, body: object): Promise<T> {
  return http().Put<T>(`/${kind}/${encodeURIComponent(id)}`, body, SILENT)
}

/**
 * Elimina una razza/classe. 409 se è usata da prototipi di mob.
 * @param kind tipo di contenuto
 * @param id id dell'elemento
 */
export async function deleteContent(kind: ContentKind, id: string): Promise<void> {
  await http().Delete(`/${kind}/${encodeURIComponent(id)}`, undefined, SILENT)
}

/**
 * Disattiva o riattiva (rinomina del file in `.yaml.disabled` e viceversa).
 * @param kind tipo di contenuto
 * @param id id dell'elemento
 * @param disabled `true` per disattivare
 */
export async function setContentDisabled<T extends IContentItem>(kind: ContentKind, id: string, disabled: boolean): Promise<T> {
  return http().Post<T>(`/${kind}/${encodeURIComponent(id)}/${disabled ? 'disable' : 'enable'}`, undefined, SILENT)
}

/** Valori ammessi per i campi dei form (flag, taglie, caratteristiche). */
export async function getContentOptions(): Promise<IContentOptions> {
  return http().Get<IContentOptions>('/options', SILENT)
}

/** Stato dei file (conteggi e data dell'ultima modifica) per il banner "riavvio necessario". */
export async function getContentStatus(): Promise<IContentStatus> {
  return http().Get<IContentStatus>('/status', { ...SILENT, meta: { autoError: false, spinner: false } })
}
