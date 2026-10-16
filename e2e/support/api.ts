/** Client REST minimale (fetch) per preparare/verificare i dati dei test senza passare dalla UI. */
import { BASE_URL } from './browser.ts'
import { credentials } from './stack.ts'

/** Risposta grezza di una chiamata API. */
export interface ApiResponse<T = any> {
  status: number
  /** `data` dell'envelope (o undefined per 204 / errori). */
  data: T
  /** Corpo JSON completo (o null). */
  body: any
}

/** Client autenticato sul backend di test. */
export class Api {
  private constructor(
    private readonly token: string,
    private readonly world?: string,
  ) {}

  /** Stesso client ma sul mondo indicato (`X-World`). */
  inWorld(world: string): Api {
    return new Api(this.token, world)
  }

  /** Esegue il login e restituisce un client pronto. */
  static async connect(): Promise<Api> {
    const response = await fetch(`${BASE_URL}/api/auth/token`, {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username: credentials.username, password: credentials.password }),
    })
    if (!response.ok) throw new Error(`Login API fallito: ${response.status}`)
    return new Api(((await response.json()) as { access_token: string }).access_token)
  }

  /**
   * Chiamata generica.
   * @param method verbo HTTP
   * @param path path comprensivo di `/api`
   * @param payload corpo JSON opzionale
   */
  async call<T = any>(method: string, path: string, payload?: unknown): Promise<ApiResponse<T>> {
    const response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: {
        authorization: `Bearer ${this.token}`,
        'content-type': 'application/json',
        ...(this.world ? { 'x-world': this.world } : {}),
      },
      body: payload === undefined ? undefined : JSON.stringify(payload),
    })
    const text = await response.text()
    const body = text ? JSON.parse(text) : null
    return { status: response.status, data: body?.data, body }
  }

  /** GET. */
  get<T = any>(path: string): Promise<ApiResponse<T>> {
    return this.call<T>('GET', path)
  }

  /** POST. */
  post<T = any>(path: string, payload: unknown): Promise<ApiResponse<T>> {
    return this.call<T>('POST', path, payload)
  }

  /** Elenco completo di una risorsa (`items`). */
  async list<T = any>(resource: string, query = ''): Promise<T[]> {
    return (await this.get<{ items: T[] }>(`/api/${resource}${query}`)).data.items
  }

  /** Elemento per vnum, o undefined. */
  async byVnum<T extends { vnum: number } = any>(resource: string, vnum: number): Promise<T | undefined> {
    return (await this.list<T>(resource)).find((item) => item.vnum === vnum)
  }
}
