"""Messaggi di transfer in it: codice stabile -> testo."""

MESSAGES: dict[str, str] = {
    "transfer.zone_not_found": "Zona non trovata",
    "transfer.no_files": "Nessun file caricato.",
    "transfer.unsupported_file": "File «{file}» non riconosciuto: servono uno zip oppure zone.yaml, rooms.yaml, mobs.yaml, objects.yaml, resets.yaml.",
    "transfer.invalid_archive": "«{file}» non è uno zip valido.",
    "transfer.file_too_large": "«{file}» supera il limite di {max_mb} MB.",
    "transfer.zone_missing": "Nel caricamento manca zone.yaml.",
    "transfer.multiple_zones": "Il caricamento contiene {count} zone: importane una alla volta.",
    "transfer.invalid_file": "File «{file}» non valido: {detail}",
    "transfer.confirm_required": "Per importare davvero servono dryRun=false e confirm=true.",
    "transfer.vnum_conflict": "Import bloccato: {count} vnum appartengono ad altre zone ({vnums}).",
}
