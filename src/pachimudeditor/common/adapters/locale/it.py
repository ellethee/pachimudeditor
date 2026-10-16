"""Messaggi di common.adapters in it: codice stabile -> testo."""

MESSAGES: dict[str, str] = {
    "world.not_found": "Mondo «{world}» non configurato.",
    "world.none_configured": "Nessun mondo configurato: aggiungere webeditor_worlds in pachimudeditor.yaml.",
    "world.capability_missing": "Il mondo selezionato non supporta questa funzione ({capability}).",
    "world.read_only": "Il mondo selezionato è in sola lettura.",
    "world.extra_unsupported": "Questo mondo non ammette campi aggiuntivi (extra).",
}
