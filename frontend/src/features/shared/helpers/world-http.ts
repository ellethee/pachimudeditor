import { currentWorldHeader } from './world-state'

/** Header che sceglie il mondo (`docs/adapters/index.md`). */
const WORLD_HEADER = 'X-World'

/**
 * `true` se l'URL è una chiamata dell'API dell'editor allo stesso origin (esclusa `/api/worlds`, che elenca i
 * mondi e non dipende da quello attivo).
 *
 * @param url - URL assoluto o relativo
 */
function isWorldScoped(url: string): boolean {
  try {
    const parsed = new URL(url, window.location.href)
    return (
      parsed.origin === window.location.origin &&
      parsed.pathname.startsWith('/api/') &&
      !parsed.pathname.startsWith('/api/worlds')
    )
  } catch {
    return false
  }
}

/**
 * Aggiunge `X-World` a ogni richiesta `/api/*` same-origin (tranne `/api/worlds`) avvolgendo `window.fetch`.
 * Il client della shell (`createPachiApp`) non espone header di default o interceptor, e l'header deve
 * coprire anche tabelle, campi remoti e download/upload che usano `fetch` direttamente: l'unico punto
 * comune è `fetch`. Da chiamare nel boot, prima di `createPachiApp`.
 */
export function installWorldHeader(): void {
  const original = window.fetch.bind(window)
  window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const world = currentWorldHeader()
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : null
    if (world && url && isWorldScoped(url)) {
      const headers = new Headers(init?.headers)
      if (!headers.has(WORLD_HEADER)) headers.set(WORLD_HEADER, world)
      return original(input, { ...init, headers })
    }
    return original(input, init)
  }
}
