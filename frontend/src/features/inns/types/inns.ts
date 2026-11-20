/** Tipi delle locande (`/api/content/inns`). */

/** Una stanza dove un reset carica il locandiere. */
export interface IInnRoom {
  vnum: number
  /** `null` se la stanza non esiste. */
  name: string | null
}

/** Una riga dell'elenco delle locande. */
export interface IInnItem {
  vnum: number
  name: string
  zoneId: number
  zoneName: string
  /** Vuoto: nessun reset lo carica, `offer` e `rent` non funzionano. */
  rooms: IInnRoom[]
}
