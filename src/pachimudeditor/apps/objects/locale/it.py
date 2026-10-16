"""Messaggi di objects in it: codice stabile -> testo."""

MESSAGES: dict[str, str] = {
    "objects.not_found": "Oggetto non trovato",
    "objects.vnum_taken": "Esiste già un oggetto con vnum {vnum}.",
    "objects.in_reset_usage": "Impossibile eliminare: l'oggetto è referenziato da {count} comandi di reset ({zones}). Aggiornali o rimuovili prima.",
    "objects.vnum_in_use": "Impossibile cambiare il vnum: l'oggetto è usato {count} volte (reset o chiavi di uscite) in: {zones}.",
    "objects.in_exit_key_usage": "Impossibile eliminare: l'oggetto è la chiave di {count} uscite ({zones}).",
    "objects.has_instances": "Impossibile eliminare: esistono {count} istanze vive dell'oggetto.",
}
