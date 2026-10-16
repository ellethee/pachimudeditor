"""Messaggi di content in it: codice stabile -> testo."""

MESSAGES: dict[str, str] = {
    "content.not_found": "Contenuto «{id}» non trovato.",
    "content.invalid_id": "Id «{id}» non valido: usa solo minuscole, cifre e underscore (max 64 caratteri).",
    "content.id_taken": "Esiste già un contenuto con id «{id}».",
    "content.id_mismatch": "L'id nel corpo («{body_id}») non coincide con quello del percorso («{id}»): l'id non è modificabile.",
    "content.invalid": "Contenuto non valido: {detail}",
    "content.race_in_use": "Impossibile eliminare la razza «{id}»: è usata da {count} prototipi di mob. Cambia prima la loro razza oppure disattivala.",
    "content.class_in_use": "Impossibile eliminare la classe «{id}»: è usata da {count} prototipi di mob. Cambia prima la loro classe oppure disattivala.",
}
