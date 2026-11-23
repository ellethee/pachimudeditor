/** Vero se il valore di un campo opzionale conta come «vuoto» (assente, stringa vuota o lista vuota). */
function isEmpty(value: unknown): boolean {
  return value == null || value === '' || (Array.isArray(value) && value.length === 0)
}

/**
 * Sistema nel corpo di un PUT parziale i campi opzionali rimasti vuoti nel form: `null` (cancella il valore) solo se il
 * record caricato ne aveva uno, quindi lo si è svuotato davvero; altrimenti la chiave si toglie, così un campo che il
 * record non restituiva o non aveva non viene azzerato (era la perdita di `debuff_skill_id`).
 * @param body corpo in costruzione (modificato sul posto)
 * @param record record caricato; assente alla creazione
 * @param keys campi opzionali da trattare
 */
export function settleClearedFields<T extends object>(body: T, record: Partial<T> | undefined, keys: (keyof T)[]): void {
  for (const key of keys) {
    if (!isEmpty(body[key])) continue
    if (record && !isEmpty(record[key])) body[key] = null as T[keyof T]
    else delete body[key]
  }
}
