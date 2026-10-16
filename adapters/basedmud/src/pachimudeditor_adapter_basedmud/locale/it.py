"""Messaggi dell'adapter BasedMud in it: codice stabile -> testo."""

MESSAGES: dict[str, str] = {
    "basedmud.unknown_flag": "Flag «{name}» sconosciuto nella tabella {table}.",
    "basedmud.extra_unknown": "Chiave di extra «{key}» sconosciuta (note: {known}).",
    "basedmud.extra_invalid": "Valore non valido per extra «{key}».",
    "basedmud.extra_readonly": "La chiave di extra «{key}» è di sola lettura.",
    "basedmud.field_unsupported": "Il campo «{field}» non esiste in ROM: è ammesso solo il valore neutro.",
    "basedmud.invalid_file_name": "Nome di file area non valido: «{name}» (solo lettere, cifre, «_», «-», «.» e suffisso .are).",
    "basedmud.file_exists": "Esiste già il file «{name}».",
    "basedmud.vnum_out_of_range": "Il vnum {vnum} è fuori dal range della zona ({bottom}-{top}).",
    "basedmud.zone_vnum_is_range": "Il vnum di una zona BasedMud coincide con il suo vnum minimo: modifica bottomVnum (richiesto {vnum}).",
    "basedmud.reset_invalid_slot": "Comando {loc}: slot di vestizione «{slot}» sconosciuto.",
}
