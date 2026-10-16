"""Messaggi di players in it: codice stabile -> testo."""

MESSAGES: dict[str, str] = {
    "players.account_not_found": "Account non trovato",
    "players.username_taken": "Esiste già un account con username «{username}».",
    "players.email_taken": "Esiste già un account con email «{email}».",
    "players.account_has_characters": "Impossibile eliminare: l'account ha {count} personaggi. Eliminali prima oppure usa l'eliminazione a cascata.",
    "players.character_not_found": "Personaggio non trovato",
    "players.name_taken": "Esiste già un personaggio di nome «{name}».",
    "players.invalid_account": "L'account {id} non esiste.",
    "players.invalid_room": "La stanza {id} non esiste.",
    "players.invalid_class": "La classe «{id}» non esiste nelle definizioni.",
    "players.invalid_race": "La razza «{id}» non esiste nelle definizioni.",
    "players.character_has_items": "Impossibile eliminare: il personaggio possiede {count} oggetti. Svuota l'inventario oppure usa l'eliminazione a cascata.",
    "players.item_not_found": "Oggetto non presente nell'inventario del personaggio",
    "players.invalid_prototype": "Prototipo di oggetto non trovato.",
    "players.prototype_required": "Indica prototypeId oppure vnum.",
    "players.item_in_container": "L'oggetto è dentro un contenitore: non può essere equipaggiato.",
}
