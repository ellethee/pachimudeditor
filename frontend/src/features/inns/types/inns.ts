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

/** Esito della creazione di un locandiere. */
export interface IInnkeeperCreated {
  vnum: number
  /** Zona dove è stato aggiunto il reset di spawn; `null` se non richiesto o fallito. */
  spawnedInZoneId: number | null
  /** Motivo per cui il reset non è stato aggiunto (il mob resta creato). */
  spawnError: string | null
}
