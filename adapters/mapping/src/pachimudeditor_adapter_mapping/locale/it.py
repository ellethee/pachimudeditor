"""Messaggi dell'adapter Mapping in it: codice stabile -> testo."""

MESSAGES: dict[str, str] = {
    "mapping.unknown_flag": "Flag «{name}» sconosciuto nella tabella {table}.",
    "mapping.unknown_name": "Nome «{name}» sconosciuto nella tabella {table}.",
    "mapping.extra_unknown": "Chiave di extra «{key}» sconosciuta (note: {known}).",
    "mapping.extra_invalid": "Valore non valido per extra «{key}».",
    "mapping.extra_readonly": "La chiave di extra «{key}» è di sola lettura.",
    "mapping.field_unsupported": "Il campo «{field}» non esiste in questo MUD: è ammesso solo il valore neutro.",
    "mapping.field_readonly": "Il campo «{field}» è di sola lettura in questa mappatura.",
    "mapping.unsupported_value": "Il valore «{value}» del campo «{field}» non è rappresentabile in questo MUD.",
    "mapping.invalid_file_name": "Nome di file non valido: «{name}» (nessun separatore, deve corrispondere a {pattern}).",
    "mapping.file_exists": "Esiste già il file «{name}».",
    "mapping.vnum_out_of_range": "Il vnum {vnum} è fuori dal range della zona ({bottom}-{top}).",
    "mapping.zone_vnum_is_range": "Il vnum di una zona coincide con un estremo del suo range: modifica il range (richiesto {vnum}).",
    "mapping.zone_top_not_last": "Con questo layout una zona nuova va in coda: topVnum {top} deve superare l'ultimo ({last}).",
    "mapping.zone_bottom_derived": "Il vnum minimo di una zona è derivato dalla zona precedente: deve essere {bottom}.",
    "mapping.zone_top_order": "Il vnum massimo {top} scavalcherebbe la zona precedente o la successiva.",
    "mapping.zone_range_has_items": "Il nuovo vnum massimo {top} sposterebbe stanze, mob o oggetti in un'altra zona.",
    "mapping.clone_unsupported": "Questo layout non supporta la clonazione di zone.",
    "mapping.unknown_style": "Stile di intestazione di zona «{style}» sconosciuto.",
    "mapping.reset_type_unsupported": "Questo MUD non ha il comando di reset {type}.",
    "mapping.reset_unmapped_commands": "La zona ha {count} comandi di reset che la mappatura non conosce: sostituire lo script li cancellerebbe.",
    "mapping.no_file_for": "Nessun file di dati può contenere record di tipo «{entity}».",
}
"""Messaggi dell'adapter Mapping: codice stabile -> testo."""
