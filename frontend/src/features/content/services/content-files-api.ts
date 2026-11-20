import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type {
  FileArea,
  IContentReload,
  IContentValidate,
  IFileContent,
  IFileEntry,
  ISkill,
  ISocial,
  ReloadKind,
} from '../types/content-files'

/** Opzioni per le richieste i cui errori sono mostrati dal chiamante (niente dialogo globale). */
const SILENT = { meta: { autoError: false }, cacheFor: 0 }

/** Client HTTP dell'app, risolto a ogni chiamata. */
function http(base = '/api/content') {
  return getUseAlovaInstance()({ url: base }).alova
}

/** Codifica un percorso relativo (`it/fight.yaml`) segmento per segmento. */
function encodePath(path: string): string {
  return path.split('/').map(encodeURIComponent).join('/')
}

/**
 * I file di un'area, strati fusi.
 * @param area `tables`, `locales` o `texts`
 */
export async function listFiles(area: FileArea): Promise<IFileEntry[]> {
  return http().Get<IFileEntry[]>(`/files/${area}`, SILENT)
}

/**
 * Il testo di un file.
 * @param area area
 * @param path percorso relativo all'area
 */
export async function getFile(area: FileArea, path: string): Promise<IFileContent> {
  return http().Get<IFileContent>(`/files/${area}/${encodePath(path)}`, SILENT)
}

/**
 * Crea o sostituisce un file nello strato dell'utente.
 * @param area area
 * @param path percorso relativo all'area
 * @param text nuovo testo
 */
export async function putFile(area: FileArea, path: string, text: string): Promise<IFileContent> {
  return http().Put<IFileContent>(`/files/${area}/${encodePath(path)}`, { text }, SILENT)
}

/**
 * Elimina il file dello strato dell'utente (torna quello di base, se c'è).
 * @param area area
 * @param path percorso relativo all'area
 */
export async function deleteFile(area: FileArea, path: string): Promise<void> {
  await http().Delete(`/files/${area}/${encodePath(path)}`, undefined, SILENT)
}

/** Le skill di tutti gli strati. */
export async function listSkills(): Promise<ISkill[]> {
  return http().Get<ISkill[]>('/skills', SILENT)
}

/**
 * Una skill con i campi avanzati.
 * @param id id della skill
 */
export async function getSkill(id: string): Promise<ISkill> {
  return http().Get<ISkill>(`/skills/${encodeURIComponent(id)}`, SILENT)
}

/**
 * Crea una skill.
 * @param body campi (camelCase) con `skillId`
 */
export async function createSkill(body: object): Promise<ISkill> {
  return http().Post<ISkill>('/skills', body, SILENT)
}

/**
 * Aggiorna una skill (solo i campi inviati).
 * @param id id della skill
 * @param body campi (camelCase)
 */
export async function updateSkill(id: string, body: object): Promise<ISkill> {
  return http().Put<ISkill>(`/skills/${encodeURIComponent(id)}`, body, SILENT)
}

/**
 * Elimina la skill dallo strato dell'utente.
 * @param id id della skill
 */
export async function deleteSkill(id: string): Promise<void> {
  await http().Delete(`/skills/${encodeURIComponent(id)}`, undefined, SILENT)
}

/** I social (strati e lingue fusi). */
export async function listSocials(): Promise<ISocial[]> {
  return http().Get<ISocial[]>('/socials', SILENT)
}

/**
 * Crea un social.
 * @param name nome
 * @param body campi del social
 */
export async function createSocial(name: string, body: object): Promise<ISocial> {
  return http().Post<ISocial>(`/socials/${encodeURIComponent(name)}`, body, SILENT)
}

/**
 * Scrive un social nello strato dell'utente.
 * @param name nome
 * @param body campi del social
 */
export async function updateSocial(name: string, body: object): Promise<ISocial> {
  return http().Put<ISocial>(`/socials/${encodeURIComponent(name)}`, body, SILENT)
}

/**
 * Toglie il social dallo strato dell'utente.
 * @param name nome
 */
export async function deleteSocial(name: string): Promise<void> {
  await http().Delete(`/socials/${encodeURIComponent(name)}`, undefined, SILENT)
}

/**
 * Il gioco controlla i file dei contenuti (`content.validate`).
 * @param strict anche gli avvisi fanno `ok = false`
 */
export async function validateContent(strict = false): Promise<IContentValidate> {
  return http('/api/world/live').Get<IContentValidate>('/content/validate', {
    ...SILENT,
    params: { strict },
    meta: { autoError: false, spinner: false },
  })
}

/**
 * Il gioco rilegge i contenuti (`content.reload`, tutto o niente).
 * @param kind cosa rileggere
 */
export async function reloadContent(kind: ReloadKind): Promise<IContentReload> {
  return http('/api/world/live').Post<IContentReload>('/content/reload', { kind }, SILENT)
}
