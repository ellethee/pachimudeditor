import { getUseAlovaInstance } from '@ilpachi/use-alova'

/** Risposta di `GET /api/health/` (liveness probe del core di pachifast). */
export interface IHealth {
  name: string
  version: string
  description: string
  database: boolean
}

/** Stato del backend. */
export async function getHealth(): Promise<IHealth> {
  return getUseAlovaInstance()({ url: '/api' }).alova.Get<IHealth>('/health/', {
    cacheFor: 0,
    meta: { autoError: false, spinner: false },
  })
}
