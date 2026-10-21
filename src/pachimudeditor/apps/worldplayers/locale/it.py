"""Messaggi di worldplayers in it: codice stabile -> testo."""

MESSAGES: dict[str, str] = {
    "worldplayers.not_found": "Giocatore non trovato.",
    "worldplayers.server_running": "Il server di gioco sembra acceso: la modifica va confermata esplicitamente (il gioco potrebbe sovrascrivere il file).",
    "worldplayers.conflict": "Il file del giocatore è cambiato dopo la lettura: ricarica e riprova.",
    "worldplayers.invalid_value": "Valore non valido per «{field}» ({reason}).",
    "worldplayers.file_unwritable": "Il file del giocatore non è modificabile ({problem}).",
    "worldplayers.unknown_object": "L'oggetto {vnum} non esiste nel mondo.",
    "worldplayers.item_not_found": "Oggetto dell'inventario non trovato.",
    "worldplayers.item_invalid": "Operazione sull'inventario non valida ({reason}).",
}
