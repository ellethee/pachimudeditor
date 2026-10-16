"""Messaggi di mobs in it: codice stabile -> testo."""

MESSAGES: dict[str, str] = {
    "mobs.not_found": "Mob non trovato",
    "mobs.vnum_taken": "Esiste già un mob con vnum {vnum}.",
    "mobs.in_reset_usage": "Impossibile eliminare: il mob è referenziato da {count} comandi di reset ({zones}). Aggiornali o rimuovili prima.",
    "mobs.vnum_in_use": "Impossibile cambiare il vnum: il mob è referenziato da {count} comandi di reset ({zones}).",
    "mobs.has_instances": "Impossibile eliminare: esistono {count} istanze vive del mob.",
}
