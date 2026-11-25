import { getUseAlovaInstance } from '@ilpachi/use-alova'
import { ResponseError } from '@ilpachi/use-alova'
import { describeError } from '../../content/helpers/describe-error'
import type { ISaveProblem, IZoneFileContent, IZoneFileEntry, IZoneFileIssue } from '../types/zonefiles'

/** Errori mostrati dal chiamante (niente dialogo globale). */
const SILENT = { meta: { autoError: false }, cacheFor: 0 }

/** Client HTTP dell'app, risolto a ogni chiamata. */
function http() {
  return getUseAlovaInstance()({ url: '/api/content' }).alova
}

/** Codifica un percorso relativo segmento per segmento. */
function encodePath(path: string): string {
  return path.split('/').map(encodeURIComponent).join('/')
}

/** I file YAML delle zone. */
export async function listZoneFiles(): Promise<IZoneFileEntry[]> {
  return http().Get<IZoneFileEntry[]>('/zonefiles', SILENT)
}

/**
 * Un file di zona con il testo.
 * @param path percorso relativo a `zones/`
 */
export async function getZoneFile(path: string): Promise<IZoneFileContent> {
  return http().Get<IZoneFileContent>(`/zonefiles/${encodePath(path)}`, SILENT)
}

/**
 * Scrive un file di zona esistente.
 * @param path percorso relativo a `zones/`
 * @param text nuovo testo
 * @param etag impronta letta (se cambiata: 409)
 */
export async function putZoneFile(path: string, text: string, etag: string): Promise<IZoneFileContent> {
  return http().Put<IZoneFileContent>(`/zonefiles/${encodePath(path)}`, { text, etag }, SILENT)
}

/**
 * Interpreta un errore di salvataggio (riga/colonna, violazioni, conflitto di etag).
 * @param e errore catturato
 */
export async function parseSaveProblem(e: unknown): Promise<ISaveProblem> {
  const message = await describeError(e)
  if (!(e instanceof ResponseError)) return { type: 'other', message, issues: [] }
  const body: unknown = await e.safeResponseJson()
  const detail = (body as { detail?: unknown } | null)?.detail
  const item = (Array.isArray(detail) ? detail[0] : undefined) as { code?: string; params?: Record<string, unknown> } | undefined
  const params = item?.params ?? {}
  const num = (v: unknown): number | undefined => (typeof v === 'number' ? v : undefined)
  if (item?.code === 'pachimud.yaml_invalid') return { type: 'yaml', message, line: num(params.line), column: num(params.column), issues: [] }
  if (item?.code === 'pachimud.zonefile_invalid') {
    return { type: 'schema', message, line: num(params.line), issues: Array.isArray(params.issues) ? (params.issues as IZoneFileIssue[]) : [] }
  }
  if (item?.code === 'pachimud.zonefile_changed') return { type: 'changed', message, issues: [] }
  return { type: 'other', message, issues: [] }
}
