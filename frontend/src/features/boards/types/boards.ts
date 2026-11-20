/** Tipi di bacheche e posta (`/api/content/boards`, `/api/content/mail`). */

/** Un oggetto BOARD che usa la bacheca. */
export interface IBoardObject {
  vnum: number
  name: string
  zoneId: number
  zoneName: string
}

/** Una bacheca con il conteggio dei messaggi. */
export interface IBoardItem {
  boardId: string
  count: number
  objects: IBoardObject[]
  /** Limite dei messaggi dal primo oggetto; `null` se non ne ha. */
  maxMessages: number | null
  /** Ha messaggi nel DB ma nessun oggetto BOARD la usa. */
  orphan: boolean
}

/** Elenco delle bacheche e tabelle del DB disponibili. */
export interface IBoardsOut {
  boardTable: boolean
  mailTable: boolean
  boards: IBoardItem[]
}

/** Un messaggio di bacheca; `number` è la posizione con cui lo legge il gioco. */
export interface IBoardMessage {
  id: number
  number: number
  author: string
  title: string
  text: string
  createdAt: string
}

/** Lettere in attesa di un destinatario. */
export interface IMailCount {
  recipient: string
  count: number
}

/** Posta in attesa, solo conteggi. */
export interface IMailOut {
  available: boolean
  total: number
  recipients: IMailCount[]
}
