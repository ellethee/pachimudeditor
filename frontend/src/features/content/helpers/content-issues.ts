import { ResponseError } from '@ilpachi/use-alova'
import type { IContentIssue } from '../types/content-files'

/**
 * I problemi (file e riga) di un `content.reload` fallito (409 `worldlive.content_reload_failed`: `detail[0].params.issues`).
 * @param error errore catturato
 * @returns i problemi, o `[]` se l'errore ne è privo
 */
export async function reloadIssues(error: unknown): Promise<IContentIssue[]> {
  if (!(error instanceof ResponseError)) return []
  const body: unknown = await error.safeResponseJson()
  const detail = body !== null && typeof body === 'object' ? (body as { detail?: unknown }).detail : undefined
  const params: unknown = Array.isArray(detail) ? (detail[0] as { params?: unknown } | undefined)?.params : undefined
  const issues = params !== null && typeof params === 'object' ? (params as { issues?: unknown }).issues : undefined
  return Array.isArray(issues) ? (issues as IContentIssue[]) : []
}
