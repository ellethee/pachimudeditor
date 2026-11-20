import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type { IBoardMessage, IBoardsOut, IMailOut } from '../types/boards'

/** Opzioni per le richieste i cui errori sono mostrati dal chiamante. */
const SILENT = { meta: { autoError: false }, cacheFor: 0 }

/** Client HTTP dell'app, risolto a ogni chiamata. */
function http() {
  return getUseAlovaInstance()({ url: '/api/content' }).alova
}

/** Le bacheche con i conteggi (`GET /api/content/boards`). */
export async function listBoards(): Promise<IBoardsOut> {
  return http().Get<IBoardsOut>('/boards', SILENT)
}

/** I messaggi di una bacheca, con ricerca opzionale (`GET /api/content/boards/{id}/messages`). */
export async function listBoardMessages(boardId: string, search: string): Promise<IBoardMessage[]> {
  return http().Get<IBoardMessage[]>(`/boards/${encodeURIComponent(boardId)}/messages`, { ...SILENT, params: search ? { search } : {} })
}

/** Posta in attesa per destinatario, solo conteggi (`GET /api/content/mail`). */
export async function getMail(): Promise<IMailOut> {
  return http().Get<IMailOut>('/mail', SILENT)
}
