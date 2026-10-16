"""Messaggi di rooms in it: codice stabile -> testo."""

MESSAGES: dict[str, str] = {
    "rooms.not_found": "Stanza non trovata",
    "rooms.exit_not_found": "Uscita non trovata",
    "rooms.extra_not_found": "Extra description non trovata",
    "rooms.vnum_taken": "Esiste già una stanza con vnum {vnum}.",
    "rooms.in_reset_usage": "Impossibile eliminare: la stanza è referenziata da {count} comandi di reset ({zones}). Aggiornali o rimuovili prima.",
    "rooms.exit_direction_taken": "Esiste già un'uscita verso {direction} da questa stanza.",
    "rooms.exit_not_in_room": "L'uscita non appartiene a questa stanza.",
    "rooms.extra_not_in_room": "L'extra description non appartiene a questa stanza.",
    "rooms.vnum_in_use": "Impossibile cambiare il vnum: la stanza è referenziata da {count} comandi di reset ({zones}).",
    "rooms.has_instances": "Impossibile eliminare: la stanza contiene {mobs} mob, {objects} oggetti ed è l'ultima stanza di {players} personaggi.",
    "rooms.exit_door_state_invalid": "Un'uscita senza porta non può essere chiusa o serrata.",
    "rooms.exit_locked_needs_key": "Un'uscita serrata richiede un keyVnum.",
    "rooms.exit_key_unknown": "L'oggetto chiave con vnum {vnum} non esiste.",
    "rooms.exit_self_loop": "Un'uscita non può portare alla stessa stanza.",
}
