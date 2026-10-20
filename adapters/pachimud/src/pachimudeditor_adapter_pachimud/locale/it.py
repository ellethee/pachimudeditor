"""Messaggi dell'adapter pachimud in it: codice stabile -> testo."""

MESSAGES: dict[str, str] = {
    "world.not_pachimud": "Questa funzione richiede un mondo di tipo pachimud (il mondo selezionato è «{kind}»).",
    "world.unavailable": "Il database del mondo non è utilizzabile (dettagli nel log del server).",
    "world.value_out_of_range": "Un valore numerico (id, pagina, vnum) è fuori dall'intervallo ammesso.",
    "world.field_unsupported": "Il campo «{field}» non esiste nello schema del database di questo mondo: è ammesso solo il valore neutro.",
    "common.editor.in_use": "Impossibile eliminare: l'elemento è ancora usato da altri dati.",
    "common.editor.invalid_reference": "Riferimento non valido: l'elemento collegato non esiste.",
    "common.editor.duplicate": "Esiste già un elemento con gli stessi valori univoci.",
    "common.editor.constraint_violation": "Operazione non consentita dai vincoli del database.",
}
